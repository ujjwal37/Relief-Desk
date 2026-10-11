from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Relief Desk API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    LOG_LEVEL: str = "INFO"

    # Gemini & ADK
    GEMINI_API_KEY: str = "replace-me"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_ENABLED: bool = True
    GEMINI_DAILY_CALL_CAP: int = 2000
    DEMO_MODE: bool = False

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
    SUPPORTED_LANGS: List[str] = ["en", "hi", "hinglish", "ta"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
