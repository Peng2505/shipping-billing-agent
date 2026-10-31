from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SAMPLES_DIR = ROOT / "data" / "samples"
EXPECTED_FILE = ROOT / "tests" / "expected" / "real_samples.yaml"
REAL_MARKERS = ("real_ocr", "real_oss", "real_llm")


def pytest_addoption(parser):
    parser.addoption(
        "--run-real", action="store_true", default=False,
        help="Run tests that call real external services (OCR / OSS / LLM).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-real"):
        return
    skip = pytest.mark.skip(reason="NOT_TESTED: real external call; run with --run-real")
    for item in items:
        if any(m in item.keywords for m in REAL_MARKERS):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def expected():
    return yaml.safe_load(EXPECTED_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES_DIR


def find_sample(pattern: str) -> Path:
    matches = sorted(SAMPLES_DIR.glob(pattern))
    assert len(matches) == 1, f"expected exactly one sample for {pattern!r}, found {matches}"
    return matches[0]
