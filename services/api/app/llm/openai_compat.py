"""Local-testing LLM provider: any OpenAI-compatible chat API, by default NVIDIA NIM.

Off unless LLM_PROVIDER=openai_compat. Refused in AI_MODE=replay/fallback and under pytest
(tests call it with a fake `post`). Replies are cached in memory only, so data/ai_cache stays
Gemini API output, and the benchmark refuses this provider unless --allow-test-provider.
The trace names it "Test model (<vendor>)", never Gemini.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings
from app.llm.antigravity import _under_pytest, extract_json

logger = logging.getLogger("relief_desk.openai_compat")

PROVIDER = "openai_compat"
_PLACEHOLDER_KEYS = {"", "replace-me", "nvapi-replace-me", "your-key"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}
_TRANSIENT = {500, 502, 503, 504}

# Learned per process: some servers reject response_format or tools with a 400.
_json_mode_ok: Optional[bool] = None
_tools_ok: Optional[bool] = None

Post = Callable[..., Any]


class ProviderError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"openai_compat HTTP {status}: {detail[:200]}")
        self.status = status


def requested() -> bool:
    return (getattr(settings, "LLM_PROVIDER", "") or "").strip().lower() == PROVIDER


def _host() -> str:
    return (urlparse(settings.OPENAI_COMPAT_BASE_URL or "").hostname or "").lower()


def has_key() -> bool:
    return (settings.OPENAI_COMPAT_API_KEY or "").strip() not in _PLACEHOLDER_KEYS


def enabled(allow_in_tests: bool = False) -> bool:
    """A local server may run without a key; a hosted one (NIM) needs a real key."""
    if not requested():
        return False
    if (settings.AI_MODE or "auto").lower() in ("replay", "fallback"):
        return False
    if _under_pytest() and not allow_in_tests:
        return False
    return has_key() or _host() in _LOCAL_HOSTS


def model() -> str:
    return (settings.OPENAI_COMPAT_MODEL or "").strip()


def embed_model() -> str:
    return (settings.OPENAI_COMPAT_EMBED_MODEL or "").strip()


def vendor() -> str:
    custom = (settings.OPENAI_COMPAT_LABEL or "").strip()
    if custom:
        return custom
    host = _host()
    if host.endswith("nvidia.com"):
        return "NVIDIA"
    if host in _LOCAL_HOSTS:
        return "local"
    return host or "OpenAI-compatible"


def label() -> str:
    return f"Test model ({vendor()})"


def _httpx_post(url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: float):
    import httpx

    try:
        return httpx.post(url, json=json, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise TimeoutError("openai_compat timed out") from exc


def _post(path: str, body: Dict[str, Any], timeout_s: Optional[float], post: Optional[Post]) -> Dict[str, Any]:
    url = (settings.OPENAI_COMPAT_BASE_URL or "").rstrip("/") + path
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if has_key():
        headers["Authorization"] = f"Bearer {settings.OPENAI_COMPAT_API_KEY.strip()}"
    timeout = float(timeout_s or settings.OPENAI_COMPAT_TIMEOUT_S or 30.0)
    send = post or _httpx_post
    for attempt in (0, 1):
        resp = send(url, json=body, headers=headers, timeout=timeout)
        status = int(getattr(resp, "status_code", 0) or 0)
        if status < 400:
            data = resp.json()
            if not isinstance(data, dict):
                raise ProviderError(status, "reply was not a JSON object")
            return data
        if status in _TRANSIENT and attempt == 0:
            logger.warning("openai_compat HTTP %d. Retrying once.", status)
            time.sleep(1.0)
            continue
        raise ProviderError(status, str(getattr(resp, "text", "") or ""))
    raise ProviderError(0, "unreachable")


def _messages(system: str, user: str) -> List[Dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _tokens(data: Dict[str, Any]) -> Optional[int]:
    total = (data.get("usage") or {}).get("total_tokens")
    return int(total) if isinstance(total, int) else None


def _message(data: Dict[str, Any]) -> Dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("openai_compat returned no choices")
    return choices[0].get("message") or {}


def chat_json(system: str, user: str, timeout_s: Optional[float] = None,
              post: Optional[Post] = None) -> Tuple[str, Optional[int]]:
    """One chat call in JSON mode. Returns (one JSON object as text, total tokens)."""
    global _json_mode_ok
    body: Dict[str, Any] = {
        "model": model(),
        "messages": _messages(system, user),
        "temperature": 0.1,
        "max_tokens": 1500,
    }
    if _json_mode_ok is not False:
        body["response_format"] = {"type": "json_object"}
    try:
        data = _post("/chat/completions", body, timeout_s, post)
    except ProviderError as exc:
        if exc.status not in (400, 422) or "response_format" not in body:
            raise
        _json_mode_ok = False
        body.pop("response_format")
        data = _post("/chat/completions", body, timeout_s, post)
    if "response_format" in body:
        _json_mode_ok = True
    text = str(_message(data).get("content") or "")
    if not text.strip():
        raise RuntimeError("openai_compat returned an empty reply")
    try:
        return extract_json(text), _tokens(data)
    except ValueError:
        # Prose instead of JSON: the caller's validator fails it and asks for one repair.
        return text.strip(), _tokens(data)


def call_function(system: str, user: str, function: Dict[str, Any], timeout_s: Optional[float] = None,
                  post: Optional[Post] = None) -> Tuple[Dict[str, Any], Optional[int], str]:
    """Force one tool call. A server without tool support gets the same schema as a JSON request.

    Returns (arguments, total tokens, "tool" or "json").
    """
    global _tools_ok
    if _tools_ok is not False:
        body = {
            "model": model(),
            "messages": _messages(system, user),
            "temperature": 0.0,
            "tools": [{"type": "function", "function": function}],
            "tool_choice": {"type": "function", "function": {"name": function["name"]}},
        }
        try:
            data = _post("/chat/completions", body, timeout_s, post)
        except ProviderError as exc:
            if exc.status not in (400, 404, 422):
                raise
            _tools_ok = False
        else:
            _tools_ok = True
            msg = _message(data)
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                if fn.get("name") not in (None, function["name"]):
                    continue
                args = fn.get("arguments")
                parsed = json.loads(args) if isinstance(args, str) else args
                if isinstance(parsed, dict):
                    return parsed, _tokens(data), "tool"
            content = str(msg.get("content") or "")
            if content.strip():
                try:
                    return json.loads(extract_json(content)), _tokens(data), "json"
                except ValueError:
                    pass
    schema = json.dumps(function["parameters"])
    text, tokens = chat_json(
        system,
        f"{user}\n\nReply with the {function['name']} arguments as one JSON object matching this JSON schema: {schema}",
        timeout_s=timeout_s,
        post=post,
    )
    return json.loads(text), tokens, "json"


def embed(texts: List[str], timeout_s: Optional[float] = None,
          post: Optional[Post] = None) -> Optional[List[List[float]]]:
    """Raw vectors from OPENAI_COMPAT_EMBED_MODEL, or None when no embedding model is set."""
    name = embed_model()
    if not name or not texts:
        return None
    body: Dict[str, Any] = {"model": name, "input": list(texts), "encoding_format": "float"}
    input_type = (settings.OPENAI_COMPAT_EMBED_INPUT_TYPE or "").strip()
    if input_type:
        body["input_type"] = input_type
    data = _post("/embeddings", body, timeout_s or settings.EMBED_TIMEOUT_S, post)
    rows = sorted(data.get("data") or [], key=lambda row: row.get("index", 0))
    vectors = [list(row.get("embedding") or []) for row in rows]
    if len(vectors) != len(texts) or not vectors[0] or any(len(v) != len(vectors[0]) for v in vectors):
        return None
    return vectors


def failure_reason(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ProviderError) and exc.status == 429:
        return "quota"
    return "error"
