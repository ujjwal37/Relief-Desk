"""Deploy files are a recipe. They must not claim a live service or commit a key."""
import json
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[3]

# Operational settings a deploy has to set. Identity defaults are not required in .env.
ENV_KEYS = [
    "LOG_LEVEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_EMBED_MODEL",
    "GEMINI_EMBED_DIM",
    "GEMINI_EMBED_TASK",
    "GEMINI_ENABLED",
    "GEMINI_DAILY_CALL_CAP",
    "GEMINI_TIMEOUT_S",
    "AI_MODE",
    "DEMO_MODE",
    "DEMO_SEED",
    "GCP_PROJECT_ID",
    "GCP_REGION",
    "FIRESTORE_EMULATOR_HOST",
    "PUBSUB_TOPIC_ALERTS",
    "GCS_BUCKET_MEDIA",
    "GOOGLE_MAPS_API_KEY",
    "API_CORS_ORIGINS",
    "SALT_PHONE_HASH",
    "JWT_SECRET",
    "FIREBASE_AUTH_EMULATOR_HOST",
    "RATE_LIMIT_REPORTS_PER_HOUR",
    "DEFAULT_LANG",
    "SUPPORTED_LANGS",
]


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_env_example_lists_every_setting_and_loads(monkeypatch):
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    parsed = _parse_env(text)
    for key in ENV_KEYS:
        assert key in parsed, key
        assert key in Settings.model_fields
    assert parsed["GEMINI_API_KEY"] == "replace-me"
    assert parsed["JWT_SECRET"] == "replace-me"
    assert parsed["GOOGLE_MAPS_API_KEY"] == "replace-me"
    assert parsed["OPENAI_COMPAT_API_KEY"] == "replace-me"
    assert parsed["SALT_PHONE_HASH"] == "replace-me"
    assert parsed["GCP_PROJECT_ID"] == "your-project-id"
    assert parsed["DEMO_SEED"] == "small"
    assert "AIza" not in text
    for key in Settings.model_fields:
        monkeypatch.delenv(key, raising=False)
    for key, value in parsed.items():
        monkeypatch.setenv(key, value)
    loaded = Settings(_env_file=None)
    assert loaded.DEMO_MODE is True
    assert loaded.DEMO_SEED == "small"
    assert loaded.GEMINI_ENABLED is True
    assert loaded.GCP_REGION == "asia-south1"
    assert loaded.JWT_SECRET == "replace-me"
    assert Settings.model_fields["JWT_SECRET"].default == ""
    assert loaded.API_CORS_ORIGINS == ["http://localhost:4200", "http://localhost:8000"]
    assert loaded.SUPPORTED_LANGS == ["en", "hi", "hinglish", "ml"]
    assert loaded.FIREBASE_AUTH_EMULATOR_HOST in ("", None)


def test_firebase_hosting_rewrites_api_and_health_to_cloud_run():
    hosting = json.loads((ROOT / "firebase.json").read_text(encoding="utf-8"))["hosting"]
    angular = json.loads((ROOT / "angular.json").read_text(encoding="utf-8"))
    output = angular["projects"]["web"]["architect"]["build"]["options"]["outputPath"]
    assert hosting["public"] == f"{output['base']}/{output['browser']}"
    assert hosting["public"] == "dist/web/browser"
    rewrites = hosting["rewrites"]
    api = next(item for item in rewrites if item["source"] == "/api/**")
    health = next(item for item in rewrites if item["source"] == "/healthz")
    expected_run = {"serviceId": "relief-desk-api", "region": "asia-south1"}
    assert api["run"] == expected_run
    assert health["run"] == expected_run
    assert rewrites[-1] == {"source": "**", "destination": "/index.html"}
    rc = json.loads((ROOT / ".firebaserc").read_text(encoding="utf-8"))
    assert rc["projects"]["default"]
    assert "AIza" not in json.dumps(rc)


def test_cloudrun_recipe_names_region_secrets_and_does_not_embed_keys():
    doc = (ROOT / "deploy" / "cloudrun.md").read_text(encoding="utf-8")
    assert "no live Cloud Run URL" in doc
    assert "in process memory" in doc
    assert "asia-south1" in doc
    assert "--set-secrets" in doc
    assert "GEMINI_API_KEY=gemini-api-key:latest" in doc
    assert "JWT_SECRET=jwt-secret:latest" in doc
    assert "There is no source default" in doc
    assert "coordinator-password" in doc
    assert "/api/auth/demo-login" in doc
    assert "GOOGLE_MAPS_API_KEY=google-maps-api-key:latest" in doc
    assert "DEMO_MODE=true" in doc
    assert "GEMINI_ENABLED=true" in doc
    assert "DEMO_SEED=small" in doc
    assert "--timeout 300" in doc
    assert "dist/web/browser" in doc
    assert '"source": "/api/**"' in doc
    assert "firebase-tools deploy --only hosting" in doc
    assert "<URL to add>" in doc
    assert "proxy.conf.js" in doc
    env_file = (ROOT / "deploy" / "cloudrun.env.yaml").read_text(encoding="utf-8")
    keys = []
    for raw in env_file.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        keys.append(line.split(":", 1)[0].strip())
    assert "DEMO_MODE" in keys
    assert "DEMO_SEED" in keys
    assert "GEMINI_ENABLED" in keys
    assert "GEMINI_API_KEY" not in keys
    assert "JWT_SECRET" not in keys
    assert "GOOGLE_MAPS_API_KEY" not in keys
    assert '"ml"' in env_file
    assert "AIza" not in env_file
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "PORT" in dockerfile
    assert "exec uvicorn" in dockerfile
    assert "--port ${PORT:-8080}" in dockerfile
    assert "DEMO_SEED=small" in dockerfile
    assert "services/api" in dockerfile
    requirements = (ROOT / "services" / "api" / "requirements.txt").read_text(encoding="utf-8")
    assert "PyJWT" in requirements
