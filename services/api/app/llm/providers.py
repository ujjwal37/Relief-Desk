"""Which model answered, named honestly, and the Gemini-only gate for scored or recorded numbers."""
from __future__ import annotations

from typing import Optional

from app.llm import antigravity as ag
from app.llm import openai_compat as oc

TEST_PROVIDERS = (ag.PROVIDER, oc.PROVIDER)


def display_name(provider: Optional[str]) -> str:
    """The words a trace row or badge shows for one call. Only real Gemini calls say Gemini."""
    if provider == oc.PROVIDER:
        return oc.label()
    if provider == ag.PROVIDER:
        return "Local test model (Antigravity)"
    if provider == "vertex":
        return "Vertex AI"
    if provider == "gemini":
        return "Gemini"
    if provider in ("cache", "replay"):
        return "Recorded (Gemini)"
    return "Rules"


def vendor(provider: Optional[str]) -> Optional[str]:
    """The name inside "Test model (...)", for the web app to fill in its own language."""
    if provider == oc.PROVIDER:
        return oc.vendor()
    if provider == ag.PROVIDER:
        return "Antigravity"
    return None


def active_test_provider() -> Optional[str]:
    if oc.requested():
        return oc.PROVIDER
    if ag.antigravity_requested():
        return ag.PROVIDER
    return None


def assert_gemini_only(where: str, allow_test_provider: bool = False) -> None:
    """Benchmark and record-ai numbers are Gemini API output only.

    Antigravity is always refused. openai_compat runs only with allow_test_provider, and the
    caller must keep those numbers out of the submission files.
    """
    ag.assert_not_antigravity(where)
    if oc.requested() and not allow_test_provider:
        raise RuntimeError(
            f"{where} refuses LLM_PROVIDER=openai_compat: benchmark and submission numbers are Gemini only. "
            "Unset LLM_PROVIDER, or pass --allow-test-provider for a local smoke run that is never a submission number."
        )
