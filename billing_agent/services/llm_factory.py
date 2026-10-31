"""Build ChatOpenAI (OpenAI-compatible) models and probe Tool Calling + Structured Output."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from billing_agent.config import LlmSettings

logger = logging.getLogger(__name__)

StructuredStrategy = Literal["provider", "tool", "unknown"]


class ProbePayload(BaseModel):
    ok: bool = Field(description="Always true when the probe succeeds")
    echo: str = Field(description="Echo the word ping")


@dataclass
class LlmCapabilities:
    tool_calling: bool
    structured_output: bool
    preferred_strategy: StructuredStrategy
    detail: str


class LlmNotConfiguredError(RuntimeError):
    pass


class LlmCapabilityError(RuntimeError):
    pass


def _thinking_extra_body(settings: LlmSettings) -> dict[str, Any] | None:
    """DeepSeek flash/V4 default to thinking mode, which rejects forced tool_choice.

    See https://api-docs.deepseek.com/guides/thinking_mode
    """
    mode = (settings.thinking or "disabled").strip().lower()
    if mode in {"disabled", "disable", "off", "false", "0"}:
        return {"thinking": {"type": "disabled"}}
    if mode in {"enabled", "enable", "on", "true", "1"}:
        return {"thinking": {"type": "enabled"}}
    return None  # auto: omit and let the provider decide


def build_chat_model(settings: LlmSettings, *, for_probe: bool = False):
    if not settings.configured:
        raise LlmNotConfiguredError(
            "LLM is not configured. Set LLM_API_KEY and LLM_MODEL in .env "
            "(optional LLM_BASE_URL for OpenAI-compatible endpoints)."
        )
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": settings.model,
        "api_key": settings.api_key,
        "temperature": 0 if for_probe else settings.temperature,
        "timeout": min(settings.timeout, 60.0) if for_probe else settings.timeout,
        "max_retries": 1 if for_probe else 2,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    extra = _thinking_extra_body(settings)
    if extra:
        kwargs["extra_body"] = extra
    return ChatOpenAI(**kwargs)


def probe_capabilities(settings: LlmSettings) -> LlmCapabilities:
    """Issue tiny real requests to verify Tool Calling and Structured Output.

    Never logs the API key. Raises LlmNotConfiguredError if unset.
    """
    model = build_chat_model(settings, for_probe=True)

    tool_ok = False
    tool_detail = ""
    try:
        def _ping(text: str) -> str:
            """Return the provided text unchanged."""
            return text

        bound = model.bind_tools([_ping])
        msg = bound.invoke("Call the _ping tool with text='pong'. Do not answer otherwise.")
        tool_ok = bool(getattr(msg, "tool_calls", None))
        tool_detail = f"tool_calls={getattr(msg, 'tool_calls', None)}"
    except Exception as exc:
        tool_detail = f"{type(exc).__name__}: {exc}"

    structured_ok = False
    preferred: StructuredStrategy = "unknown"
    struct_detail = ""
    try:
        structured = model.with_structured_output(ProbePayload)
        result = structured.invoke("Return ok=true and echo='ping'.")
        if isinstance(result, ProbePayload) and result.ok and result.echo.lower() == "ping":
            structured_ok = True
            preferred = "provider"
            struct_detail = "provider_structured_output_ok"
        elif isinstance(result, dict) and result.get("ok") and str(result.get("echo", "")).lower() == "ping":
            structured_ok = True
            preferred = "provider"
            struct_detail = "provider_structured_output_ok_dict"
        else:
            struct_detail = f"unexpected_result={result!r}"
    except Exception as exc:
        struct_detail = f"{type(exc).__name__}: {exc}"

    if not structured_ok and tool_ok:
        # ToolStrategy can still work via create_agent when provider SO fails
        preferred = "tool"
        structured_ok = True
        struct_detail += "; falling_back_to_tool_strategy"

    detail = f"tools[{tool_detail}]; structured[{struct_detail}]"
    logger.info("LLM capability probe: tools=%s structured=%s strategy=%s", tool_ok, structured_ok, preferred)
    return LlmCapabilities(
        tool_calling=tool_ok,
        structured_output=structured_ok,
        preferred_strategy=preferred,
        detail=detail,
    )
