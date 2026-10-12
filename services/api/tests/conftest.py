"""Tests never spend Gemini quota, whatever is in the developer's services/api/.env.

The environment is set before the app is imported (settings read it at import),
and an autouse fixture puts the placeholder key back for every test, so gemini_live() is False. Tests that need
"live" Gemini set a fake key themselves and mock the client.
"""
import os

os.environ["GEMINI_API_KEY"] = "replace-me"

import pytest  # noqa: E402

from app.config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_gemini(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "replace-me")
    yield