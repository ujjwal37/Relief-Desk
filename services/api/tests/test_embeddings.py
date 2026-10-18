"""Mocked test for the single gemini_call log line emitted by embeddings."""
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.config import settings
from app.llm import embeddings


def test_embed_texts_emits_gemini_call_log(monkeypatch, caplog):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-live-gemini-key")
    monkeypatch.setattr(settings, "GEMINI_EMBED_MODEL", "gemini-embedding-001")
    monkeypatch.setattr(settings, "GEMINI_EMBED_DIM", 768)

    mock_embedding = SimpleNamespace(values=[0.05] * 768)
    mock_result = SimpleNamespace(embeddings=[mock_embedding])

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = mock_result

    monkeypatch.setattr(
        "app.llm.client.build_genai_client",
        lambda timeout_s=3.0, force_studio=False: (mock_client, "vertex"),
    )

    with caplog.at_level(logging.INFO, logger="relief_desk.llm"):
        vectors = embeddings.embed_texts(["Flood near Gandhi school"])

    assert vectors is not None
    assert len(vectors) == 1
    assert len(vectors[0]) == 768

    gemini_logs = [r.message for r in caplog.records if "gemini_call" in r.message]
    assert len(gemini_logs) == 1
    log_line = gemini_logs[0]
    assert "provider=vertex" in log_line
    assert "model=gemini-embedding-001" in log_line
    assert "ok=true" in log_line
    assert "fallback_reason=none" in log_line
    assert "latency_ms=" in log_line
    # Ensure no keys or raw text are leaked into the log line
    assert "Flood near Gandhi school" not in log_line
    assert "fake-live-gemini-key" not in log_line
