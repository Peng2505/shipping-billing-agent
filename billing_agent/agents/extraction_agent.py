"""LangChain single-agent extractor: create_agent + tools + Pydantic structured output."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from billing_agent.agents.document_index import DocumentIndex
from billing_agent.agents.grounding import ground_extraction
from billing_agent.agents.prompts import SYSTEM_PROMPT, build_user_prompt
from billing_agent.agents.tools import EXTRACTION_TOOLS, ExtractionContext
from billing_agent.config import LlmSettings
from billing_agent.schemas import ExtractionResult, GroundedExtraction, ParsedDocument
from billing_agent.services.llm_factory import (
    LlmCapabilities,
    LlmCapabilityError,
    LlmNotConfiguredError,
    build_chat_model,
    probe_capabilities,
)

logger = logging.getLogger(__name__)


class ExtractionAgentError(RuntimeError):
    pass


def _inventory_summary(index: DocumentIndex, limit: int = 30) -> str:
    rows = index.inventory()[:limit]
    return json.dumps(rows, ensure_ascii=False, indent=1)


def _extract_structured(result: dict[str, Any]) -> ExtractionResult:
    structured = result.get("structured_response")
    if structured is None:
        raise ExtractionAgentError(
            "Agent finished without a structured_response. "
            "The model may not support Tool Calling + Structured Output together."
        )
    if isinstance(structured, ExtractionResult):
        return structured
    if isinstance(structured, dict):
        return ExtractionResult.model_validate(structured)
    raise ExtractionAgentError(f"Unexpected structured_response type: {type(structured)!r}")


class ExtractionAgent:
    def __init__(
        self,
        settings: LlmSettings,
        *,
        capabilities: LlmCapabilities | None = None,
        model: Any | None = None,
        skip_probe: bool = False,
    ) -> None:
        self.settings = settings
        self._model = model
        self._capabilities = capabilities
        self._agent = None
        self._strategy_name: str | None = None
        self._skip_probe = skip_probe

    @classmethod
    def from_settings(cls, settings: LlmSettings) -> ExtractionAgent:
        return cls(settings)

    @property
    def configured(self) -> bool:
        return self.settings.configured or self._model is not None

    def ensure_ready(self) -> LlmCapabilities:
        if self._agent is not None and self._capabilities is not None:
            return self._capabilities

        if self._model is None:
            self._model = build_chat_model(self.settings)

        if self._capabilities is None:
            if self._skip_probe:
                self._capabilities = LlmCapabilities(
                    tool_calling=True, structured_output=True,
                    preferred_strategy="provider", detail="probe_skipped",
                )
            else:
                self._capabilities = probe_capabilities(self.settings)

        caps = self._capabilities
        if not caps.tool_calling:
            raise LlmCapabilityError(
                f"Configured model does not support Tool Calling. Probe detail: {caps.detail}"
            )
        if not caps.structured_output:
            raise LlmCapabilityError(
                f"Configured model does not support Structured Output. Probe detail: {caps.detail}"
            )

        from langchain.agents import create_agent
        from langchain.agents.structured_output import ProviderStrategy, ToolStrategy

        if caps.preferred_strategy == "provider":
            # Prefer provider-native SO when the probe confirmed it.
            response_format = ProviderStrategy(ExtractionResult)
            self._strategy_name = "ProviderStrategy"
        else:
            # DeepSeek flash/V4: native response_format is unavailable; ToolStrategy
            # works when thinking mode is disabled (see llm_factory extra_body).
            response_format = ToolStrategy(ExtractionResult)
            self._strategy_name = "ToolStrategy"

        self._agent = create_agent(
            model=self._model,
            tools=EXTRACTION_TOOLS,
            system_prompt=SYSTEM_PROMPT,
            response_format=response_format,
            context_schema=ExtractionContext,
            name="shipping_extraction_agent",
        )
        return caps

    def extract(self, document: ParsedDocument) -> GroundedExtraction:
        if not self.configured:
            raise LlmNotConfiguredError(
                "LLM is not configured. Set LLM_API_KEY and LLM_MODEL (see .env.example)."
            )
        self.ensure_ready()
        assert self._agent is not None

        index = DocumentIndex.from_document(document)
        if not index.block_order:
            empty = ExtractionResult(warnings=["Document has no source blocks to extract from."])
            return ground_extraction(empty, index, model_name=self.settings.model,
                                     structured_strategy=self._strategy_name)

        tool_trace: list = []
        context = ExtractionContext(index=index, tool_trace=tool_trace)
        user_prompt = build_user_prompt(
            document.file_name, document.source_chain, _inventory_summary(index),
        )

        started = time.monotonic()
        try:
            result = self._agent.invoke(
                {"messages": [{"role": "user", "content": user_prompt}]},
                context=context,
            )
        except Exception as exc:
            raise ExtractionAgentError(f"Agent invoke failed: {type(exc).__name__}: {exc}") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)

        raw = _extract_structured(result)
        grounded = ground_extraction(
            raw,
            index,
            tool_trace=tool_trace,
            model_name=getattr(self._model, "model_name", None) or self.settings.model,
            structured_strategy=self._strategy_name,
            elapsed_ms=elapsed_ms,
        )
        logger.info(
            "Extraction done file=%s charges=%d excluded=%d issues=%d tools=%d ms=%d",
            document.file_name,
            len(grounded.actual_charges),
            len(grounded.excluded_charges),
            len(grounded.issues),
            len(tool_trace),
            elapsed_ms,
        )
        return grounded
