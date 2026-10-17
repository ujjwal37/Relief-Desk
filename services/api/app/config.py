from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Relief Desk API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    LOG_LEVEL: str = "INFO"

    # Model stays configurable: 2.5 Flash returned 404 for this account on 14 Oct.
    # https://ai.google.dev/gemini-api/docs/models
    GEMINI_API_KEY: str = "replace-me"
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBED_DIM: int = 768
    GEMINI_EMBED_TASK: str = "SEMANTIC_SIMILARITY"
    GEMINI_ENABLED: bool = True
    GEMINI_DAILY_CALL_CAP: int = 2000
    GEMINI_TIMEOUT_S: float = 20.0
    # Model calls that may run at once (Gemini or a local model). Extra calls wait in a
    # priority queue, critical cases first. Set 1 for a local model that serves one call at a time.
    AI_CONCURRENCY: int = 2
    # Live demo and a judge's own report share this cap. 8 matches the free-tier pace.
    GEMINI_RPM: int = 8
    GEMINI_RPM_ALL: int = 12
    # Duplicate retrieval must answer inside the 5 s merge budget, or the lexical rules decide.
    EMBED_TIMEOUT_S: float = 3.0
    # auto: call Gemini when a real key is set. replay: serve data/ai_cache.
    # fallback: never call the network. DEMO_MODE does not skip a real key.
    AI_MODE: str = "auto"
    # Manual testing only: "antigravity" routes live calls to the local Antigravity CLI (agy),
    # "openai_compat" to an OpenAI-compatible chat API such as NVIDIA NIM. Neither is ever
    # scored by the benchmark or written to data/ai_cache.
    LLM_PROVIDER: str = ""
    ANTIGRAVITY_BIN: str = ""
    ANTIGRAVITY_TIMEOUT_S: float = 40.0
    OPENAI_COMPAT_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    OPENAI_COMPAT_API_KEY: str = ""
    OPENAI_COMPAT_MODEL: str = "meta/llama-3.3-70b-instruct"
    # Empty means no embedding call: duplicates use local similarity and rules.
    OPENAI_COMPAT_EMBED_MODEL: str = ""
    # NIM retrieval embedders require input_type. Empty sends none (plain OpenAI servers reject it).
    OPENAI_COMPAT_EMBED_INPUT_TYPE: str = "query"
    OPENAI_COMPAT_TIMEOUT_S: float = 30.0
    # Name in the trace label "Test model (<name>)". Empty derives it from the base URL host.
    OPENAI_COMPAT_LABEL: str = ""
    DEMO_MODE: bool = True
    # "production" on Cloud Run. Locally it stays "development", where the fixed demo token
    # and the demo password still work for dev and tests.
    ENV: str = "development"
    # Optional password for the coordinator form in production. Empty means only the
    # one-click demo login (DEMO_MODE) can sign in there.
    COORDINATOR_PASSWORD: str = ""
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
