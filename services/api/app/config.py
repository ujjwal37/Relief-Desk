from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Relief Desk API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    LOG_LEVEL: str = "INFO"

    # Gemini & ADK. Model ids from https://ai.google.dev/gemini-api/docs/models
    # (page updated 2026-10-09). New projects use gemini-3.8-flash.
    # Embeddings: gemini-embedding-001, task SEMANTIC_SIMILARITY, 768 dimensions
    # (https://ai.google.dev/gemini-api/docs/embeddings).
    GEMINI_API_KEY: str = "replace-me"
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBED_DIM: int = 768
    GEMINI_EMBED_TASK: str = "SEMANTIC_SIMILARITY"
    GEMINI_ENABLED: bool = True
    GEMINI_DAILY_CALL_CAP: int = 2000
    GEMINI_TIMEOUT_S: float = 12.0
    # auto: call Gemini when a real key is set. replay: serve data/ai_cache.
    # fallback: never call the network. DEMO_MODE does not skip a real key.
    AI_MODE: str = "auto"
    # Manual testing only: "antigravity" routes live calls to the local Antigravity CLI (agy).
    LLM_PROVIDER: str = ""
    ANTIGRAVITY_BIN: str = ""
    ANTIGRAVITY_TIMEOUT_S: float = 40.0
    DEMO_MODE: bool = True
    # small: two cases and a few teams. full: the flood pack (benchmark and record_ai read the files directly).
    DEMO_SEED: str = "small"

    # Google Cloud
    GCP_PROJECT_ID: str = "relief-desk-demo"
    GCP_REGION: str = "asia-south1"
    FIRESTORE_EMULATOR_HOST: Optional[str] = "127.0.0.1:8080"
    PUBSUB_TOPIC_ALERTS: str = "alerts"
    GCS_BUCKET_MEDIA: str = "relief-desk-media"

    # Maps
    GOOGLE_MAPS_API_KEY: str = "replace-me"

    # App security & throttling
    API_CORS_ORIGINS: List[str] = ["http://localhost:4200", "http://localhost:8000"]
    SALT_PHONE_HASH: str = "synthetic-salt"
    JWT_SECRET: str = "relief-desk-coordinator-secret-2026"
    FIREBASE_AUTH_EMULATOR_HOST: Optional[str] = None
    RATE_LIMIT_REPORTS_PER_HOUR: int = 10
    DEFAULT_LANG: str = "en"
    SUPPORTED_LANGS: List[str] = ["en", "hi", "hinglish", "ml"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
