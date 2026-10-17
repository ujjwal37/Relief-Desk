"""Local-only LLM provider for manual testing: the Antigravity CLI (`agy`) on the developer's PC.

Off unless LLM_PROVIDER=antigravity. Refused in AI_MODE=replay and under pytest, and never used by
the benchmark or record-ai (see `assert_not_antigravity`). Replies are not written to the replay
cache, so recordings stay pure Gemini API output.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger("relief_desk.antigravity")

PROVIDER = "antigravity-local"
MODEL = "antigravity-cli"
# The CLI has returned an empty body after several minutes when its own timer is ignored.
# This cap applies to both --print-timeout and the subprocess, whatever the setting says.
HARD_TIMEOUT_S = 40.0


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


def _bounded_timeout(timeout_s: Optional[float]) -> float:
    if timeout_s is None:
        timeout_s = getattr(settings, "ANTIGRAVITY_TIMEOUT_S", HARD_TIMEOUT_S)
    try:
        requested = float(timeout_s or HARD_TIMEOUT_S)
    except (TypeError, ValueError):
        requested = HARD_TIMEOUT_S
    return max(1.0, min(requested, HARD_TIMEOUT_S))


def _log_raw(message: str, stdout: Optional[str], stderr: Optional[str]) -> None:
    logger.error(
        "%s | stdout=%r | stderr=%r",
        message,
        (stdout or "")[:2000],
        (stderr or "")[:2000],
    )


def _json_obj(blob: str) -> Optional[Dict[str, Any]]:
    clean = (blob or "").strip()
    if not clean:
        return None
    try:
        data = json.loads(clean)
    except ValueError:
        try:
            data = json.loads(extract_json(clean))
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def _reply_from_stdout(stdout: str) -> Tuple[str, Optional[int]]:
    """Read the CLI envelope from any line, or a bare JSON object if that is all it printed."""
    raw = stdout or ""
    blobs = [line.strip() for line in raw.splitlines() if line.strip()]
    whole = raw.strip()
    if whole and whole not in blobs:
        blobs.append(whole)
    envelopes = []
    bare = []
    for blob in reversed(blobs):
        data = _json_obj(blob)
        if data is None:
            continue
        if any(key in data for key in ("status", "response", "usage", "text")):
            envelopes.append(data)
        else:
            bare.append(data)
    if envelopes:
        data = envelopes[0]
        status = str(data.get("status", "SUCCESS")).upper()
        if status not in ("SUCCESS", "OK", ""):
            raise RuntimeError(f"Antigravity CLI status {data.get('status')}")
        text = str(data.get("response") or data.get("text") or "")
        if not text.strip():
            raise RuntimeError("Antigravity CLI returned an empty reply")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        tokens = usage.get("total_tokens")
        return text, int(tokens) if isinstance(tokens, int) else None
    if bare:
        return json.dumps(bare[0], ensure_ascii=False), None
    text = raw.strip()
    if text:
        return text, None
    raise RuntimeError("Antigravity CLI returned an empty reply")


def call_antigravity(system_instruction: str, user_prompt: str, timeout_s: Optional[float] = None,
                     run=subprocess.run) -> Tuple[str, Optional[int]]:
    """One non-interactive `agy --print` call. Returns (reply text, total tokens). Raises on failure."""
    timeout_s = _bounded_timeout(timeout_s)
    prompt = (
        f"{system_instruction}\n\n{user_prompt}\n\n"
        "Answer directly. Do not use tools, do not read or write files. Return only the requested output."
    )
    workdir = tempfile.mkdtemp(prefix="rd-agy-")  # empty dir: the CLI agent has no project files to touch
    cmd = [_binary(), "--print", prompt, "--output-format", "json", "--disable-slash-commands",
           "--print-timeout", f"{int(timeout_s)}s"]
    try:
        proc = run(cmd, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
                   timeout=timeout_s, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        _log_raw("Antigravity CLI timed out", getattr(exc, "stdout", None), getattr(exc, "stderr", None))
        raise TimeoutError("Antigravity CLI timed out") from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if proc.returncode not in (0, None):
        _log_raw(f"Antigravity CLI exit {proc.returncode}", proc.stdout, proc.stderr)
        raise RuntimeError(f"Antigravity CLI exit {proc.returncode}: {(proc.stderr or '')[:200]}")
    try:
        return _reply_from_stdout(proc.stdout or "")
    except RuntimeError as exc:
        _log_raw(str(exc), proc.stdout, proc.stderr)
        raise


_LOCAL_BASE = None


def gemini_base_is_local() -> bool:
    """True when the Gemini SDK is pointed at a localhost base (the local test AI), so its answers are not labelled Gemini."""
    global _LOCAL_BASE
    if _LOCAL_BASE is None:
        import os
        from urllib.parse import urlparse
        base = os.environ.get("GOOGLE_GEMINI_BASE_URL") or ""
        try:
            import google.genai as _genai  # type: ignore
            base = base or str(_genai.Client(api_key="unused")._api_client._http_options.base_url or "")
        except Exception:
            pass
        _LOCAL_BASE = (urlparse(base).hostname or "") in ("127.0.0.1", "localhost", "0.0.0.0")
    return _LOCAL_BASE
