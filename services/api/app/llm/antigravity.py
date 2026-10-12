"""Local-only LLM provider for manual testing: the Antigravity CLI (`agy`) on the developer's PC.

Off unless LLM_PROVIDER=antigravity. Refused in AI_MODE=replay and under pytest, and never used by
the benchmark or record-ai (see `assert_not_antigravity`). Replies are not written to the replay
cache, so recordings stay pure Gemini API output.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

from app.config import settings

PROVIDER = "antigravity-local"
MODEL = "antigravity-cli"


def _under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def antigravity_requested() -> bool:
    return (getattr(settings, "LLM_PROVIDER", "") or "").strip().lower() == "antigravity"


def antigravity_enabled(allow_in_tests: bool = False) -> bool:
    if not antigravity_requested():
        return False
    if (settings.AI_MODE or "auto").lower() in ("replay", "fallback"):
        return False
    if _under_pytest() and not allow_in_tests:
        return False
    return True


def assert_not_antigravity(where: str) -> None:
    """Benchmark and record-ai must only score or store real Gemini API output."""
    if antigravity_requested():
        raise RuntimeError(f"{where} refuses LLM_PROVIDER=antigravity; unset it and use the Gemini API.")


def extract_json(text: str) -> str:
    """Pull one JSON object out of a reply that may carry fences or prose."""
    clean = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", clean, re.S)
    if fence:
        clean = fence.group(1).strip()
    if not clean.startswith("{"):
        start, end = clean.find("{"), clean.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in Antigravity reply")
        clean = clean[start:end + 1]
    json.loads(clean)
    return clean


def _binary() -> str:
    path = getattr(settings, "ANTIGRAVITY_BIN", "") or shutil.which("agy") or shutil.which("antigravity")
    if not path:
        raise FileNotFoundError("Antigravity CLI (agy) not found on PATH")
    return path


def call_antigravity(system_instruction: str, user_prompt: str, timeout_s: Optional[float] = None,
                     run=subprocess.run) -> Tuple[str, Optional[int]]:
    """One non-interactive `agy --print` call. Returns (reply text, total tokens). Raises on failure."""
    timeout_s = float(timeout_s or getattr(settings, "ANTIGRAVITY_TIMEOUT_S", 60.0) or 60.0)
    prompt = (
        f"{system_instruction}\n\n{user_prompt}\n\n"
        "Answer directly. Do not use tools, do not read or write files. Return only the requested output."
    )
    workdir = tempfile.mkdtemp(prefix="rd-agy-")  # empty dir: the CLI agent has no project files to touch
    cmd = [_binary(), "--print", prompt, "--output-format", "json", "--disable-slash-commands",
           "--print-timeout", f"{int(timeout_s)}s"]
    try:
        proc = run(cmd, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
                   timeout=timeout_s + 10, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("Antigravity CLI timed out") from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if proc.returncode not in (0, None):
        raise RuntimeError(f"Antigravity CLI exit {proc.returncode}: {(proc.stderr or '')[:200]}")
    try:
        env = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("Antigravity CLI did not return its JSON envelope") from exc
    if str(env.get("status", "")).upper() != "SUCCESS":
        raise RuntimeError(f"Antigravity CLI status {env.get('status')}")
    text = str(env.get("response") or "")
    if not text.strip():
        raise RuntimeError("Antigravity CLI returned an empty reply")
    tokens = (env.get("usage") or {}).get("total_tokens")
    return text, int(tokens) if isinstance(tokens, int) else None
