"""Stable per-team share tokens. The secret stays in the API config."""
import hashlib
import secrets

from app.config import settings


def team_share_token(resource_id: str) -> str:
    raw = hashlib.sha256(
        f"relief-desk-team:{settings.JWT_SECRET}:{resource_id}".encode()
    ).hexdigest()[:20]
    return f"tm_{raw}"


def token_matches(resource_id: str, supplied: str | None) -> bool:
    if not supplied:
        return False
    expected = team_share_token(resource_id).encode()
    given = supplied.encode()
    if len(given) != len(expected):
        return False
    return secrets.compare_digest(given, expected)
