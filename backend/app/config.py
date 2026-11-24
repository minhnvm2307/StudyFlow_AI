import os
import logging
from dotenv import load_dotenv

# In production (Railway), env vars are injected by the platform.
# override=False ensures Railway's vars take precedence over any .env file.
_is_production = os.getenv("APP_ENV", "").lower() == "production"
load_dotenv(override=not _is_production)

class Settings:
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "4000"))
    ENV: str = os.getenv("APP_ENV", os.getenv("ENV", "development")).lower()
    ALLOW_DESTRUCTIVE_DEV_ENDPOINTS: bool = os.getenv("ALLOW_DESTRUCTIVE_DEV_ENDPOINTS", "false").lower() == "true"

    # Storage
    STUDYFLOW_DB_PATH: str = os.getenv("STUDYFLOW_DB_PATH", "data/studyflow.local.json")
    FILE_DB_PATH: str = os.getenv("FILE_PATH", "data/upload")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://studyflow:studyflow@localhost:5432/studyflow",
    )
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    S3_REGION: str = os.getenv("S3_REGION", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")

    # Logging / observability
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    # Default to false in production (Railway has ephemeral filesystem)
    LOG_TO_FILE: bool = os.getenv(
        "LOG_TO_FILE",
        "false" if os.getenv("APP_ENV", "").lower() == "production" else "true"
    ).lower() != "false"
    LOG_BODIES: bool = os.getenv("LOG_BODIES", "true").lower() != "false"
    LOG_BODY_MAX_CHARS: int = int(os.getenv("LOG_BODY_MAX_CHARS", "20000"))
    LOG_REQUEST_OUTPUT: bool = os.getenv("LOG_REQUEST_OUTPUT", "true").lower() != "false"
    LOG_DEBUG_HINTS: bool = os.getenv("LOG_DEBUG_HINTS", "true").lower() != "false"
    LOG_FILE_MAX_BYTES: int = int(os.getenv("LOG_FILE_MAX_BYTES", "10485760"))
    LOG_FILE_BACKUP_COUNT: int = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))

    # LLM
    LLM_PROVIDER: str = os.getenv(
        "LLM_PROVIDER",
        "openrouter" if os.getenv("OPENROUTER_API_KEY") else "nvidia" if os.getenv("NVIDIA_API_KEY") else "openai",
    ).lower()
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "")
    OPENROUTER_REFERER: str = os.getenv("OPENROUTER_REFERER", "")
    OPENROUTER_APP_TITLE: str = os.getenv("OPENROUTER_APP_TITLE", "StudyFlow AI")
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "")
    CUSTOM_URL: str = os.getenv("CUSTOM_URL", "http://localhost:20128/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    CUSTOM_API_KEY: str = os.getenv("CUSTOM_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_TOP_P: float | None = float(os.getenv("LLM_TOP_P")) if os.getenv("LLM_TOP_P") else None
    LLM_MAX_TOKENS: int | None = int(os.getenv("LLM_MAX_TOKENS")) if os.getenv("LLM_MAX_TOKENS") else None
    LLM_TIMEOUT_MS: int = int(os.getenv("LLM_TIMEOUT_MS", "90000"))

    def __init__(self):
        provider = self.LLM_PROVIDER
        if provider == "openrouter":
            self.CUSTOM_URL = self.OPENROUTER_BASE_URL or self.CUSTOM_URL
            self.CUSTOM_API_KEY = self.OPENROUTER_API_KEY or self.CUSTOM_API_KEY
            self.LLM_MODEL = self.OPENROUTER_MODEL or self.LLM_MODEL
        elif provider == "nvidia":
            self.CUSTOM_URL = self.NVIDIA_BASE_URL or self.CUSTOM_URL
            self.CUSTOM_API_KEY = self.NVIDIA_API_KEY or self.CUSTOM_API_KEY
            self.LLM_MODEL = self.NVIDIA_MODEL or self.LLM_MODEL
        elif provider == "openai":
            self.CUSTOM_URL = self.OPENAI_BASE_URL or self.CUSTOM_URL
            self.CUSTOM_API_KEY = self.OPENAI_API_KEY or self.CUSTOM_API_KEY
            self.LLM_MODEL = self.OPENAI_MODEL or self.LLM_MODEL or "gpt-4o-mini"

        if self.CUSTOM_API_KEY:
            self.CUSTOM_API_KEY = self.CUSTOM_API_KEY.strip().strip('"').strip("'")

    # FSRS
    FSRS_TUNING_THRESHOLD: int = int(os.getenv("FSRS_TUNING_THRESHOLD", "1000"))
    DESIRED_RETENTION_SEMESTER: float = 0.85
    DESIRED_RETENTION_SPRINT: float = 0.90

    # Document processing
    MAX_SECTIONS_PER_SUBJECT: int = int(os.getenv("MAX_SECTIONS_PER_SUBJECT", "10"))
    MERGE_JACCARD_THRESHOLD: float = float(os.getenv("MERGE_JACCARD_THRESHOLD", "0.75"))
    LOW_INFO_DOC_CHAR_THRESHOLD: int = int(os.getenv("LOW_INFO_DOC_CHAR_THRESHOLD", "300"))
    MAX_DOCUMENT_CHARS_FOR_LLM: int = int(os.getenv("MAX_DOCUMENT_CHARS_FOR_LLM", "25000"))
    TOPIC_EXTRACTION_MODE: str = os.getenv("TOPIC_EXTRACTION_MODE", "llm").lower()
    LLM_TOPICS_MAX_PER_CHAPTER: int = int(os.getenv("LLM_TOPICS_MAX_PER_CHAPTER", "3"))
    LLM_TOPICS_MAX_PER_SOURCE: int = int(os.getenv("LLM_TOPICS_MAX_PER_SOURCE", "36"))
    LLM_TOPIC_CHARS_PER_CHAPTER: int = int(os.getenv("LLM_TOPIC_CHARS_PER_CHAPTER", "6000"))

    # Scheduler weights (urgency formula)
    URGENCY_W1_WEAKNESS: float = float(os.getenv("URGENCY_W1", "0.25"))
    URGENCY_W2_EXAM_FACTOR: float = float(os.getenv("URGENCY_W2", "0.20"))
    URGENCY_W3_IMPORTANCE: float = float(os.getenv("URGENCY_W3", "0.25"))
    URGENCY_W4_FORGETTING: float = float(os.getenv("URGENCY_W4", "0.30"))

    # Session
    MAX_DAILY_TASK_MINUTES: int = int(os.getenv("MAX_DAILY_TASK_MINUTES", "45"))
    MIN_DAILY_TASK_MINUTES: int = int(os.getenv("MIN_DAILY_TASK_MINUTES", "5"))
    DEFAULT_DAILY_GOAL_MINUTES: int = int(os.getenv("DEFAULT_DAILY_GOAL_MINUTES", "30"))
    TOP_TOPICS_PER_DAY: int = int(os.getenv("TOP_TOPICS_PER_DAY", "3"))

    # CP-SAT
    CP_SOLVER_TIMEOUT_SECONDS: float = float(os.getenv("CP_SOLVER_TIMEOUT", "1.0"))
    CP_MAX_SLACK_PERCENT: float = float(os.getenv("CP_MAX_SLACK_PERCENT", "0.20"))

    # XP rewards
    XP_PER_CORRECT_ANSWER: int = int(os.getenv("XP_PER_CORRECT_ANSWER", "10"))

    # JWT Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "studyflow-secret-key-super-secure")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "10080"))

settings = Settings()

# Warn if JWT_SECRET is the default in production
if settings.ENV == "production" and settings.JWT_SECRET == "studyflow-secret-key-super-secure":
    logging.getLogger("studyflow").warning(
        "[SECURITY] JWT_SECRET is using the default value in production! "
        "Set JWT_SECRET env var to a strong random string."
    )

# Backward-compat aliases (used by existing imports)
CUSTOM_URL = settings.CUSTOM_URL
MAX_SECTIONS_PER_SUBJECT = settings.MAX_SECTIONS_PER_SUBJECT
FSRS_TUNING_THRESHOLD = settings.FSRS_TUNING_THRESHOLD
FILE_DB_PATH = settings.FILE_DB_PATH
STUDYFLOW_DB_PATH = settings.STUDYFLOW_DB_PATH
MERGE_JACCARD_THRESHOLD = settings.MERGE_JACCARD_THRESHOLD
LOW_INFO_DOC_CHAR_THRESHOLD = settings.LOW_INFO_DOC_CHAR_THRESHOLD
DESIRED_RETENTION_SEMESTER = settings.DESIRED_RETENTION_SEMESTER
DESIRED_RETENTION_SPRINT = settings.DESIRED_RETENTION_SPRINT
