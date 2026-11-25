from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Application configuration loaded from the project root .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "PlaceCall AI"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str

    # Auth
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # AI / LLM
    GROQ_API_KEY: str
    GROQ_FAST_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_REASONING_MODEL: str = "qwen/qwen3.8-27b"
    GEMINI_API_KEY: str | None = None
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # Vapi Voice AI (Primary Telephony + Web Calls)
    VAPI_API_KEY: str
    VAPI_PUBLIC_KEY: str
    VAPI_PHONE_NUMBER_ID: str
    VAPI_PHONE_NUMBER: str | None = None
    VAPI_ASSISTANT_ID: str
    VAPI_BASE_URL: str = "https://api.vapi.ai"

    # Optional Twilio (kept optional for legacy/WhatsApp sandbox)
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_PHONE_NUMBER: str | None = None
    PHONE_NUMBER: str | None = None
    TWILIO_VOICE_MODE: str = Field(
        default="gather",
        description="Legacy Twilio mode if used.",
    )
    TWILIO_WHATSAPP_FROM: str | None = None
    VALIDATE_TWILIO_SIGNATURE: bool = False

    # Public URL & Notifications
    PUBLIC_BASE_URL: str = "http://localhost:8080"
    SMTP_EMAIL: str | None = None
    SMTP_APP_PASSWORD: str | None = None

    # Matching
    DEFAULT_FIT_THRESHOLD: int = 70

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        url = v.strip()
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @field_validator("PUBLIC_BASE_URL")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.strip().rstrip("/")


settings = Settings()
