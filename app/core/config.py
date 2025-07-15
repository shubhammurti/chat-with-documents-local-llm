from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import validator
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # --- API Keys ---
    GOOGLE_API_KEY: str
    GROQ_API_KEY: str

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    PUBLIC_API_URL: str = "http://localhost:8000" # Add this line
    FRONTEND_URL: str = "http://localhost:8501"
    GOOGLE_OAUTH_REDIRECT_URI: Optional[str] = None

    @validator("GOOGLE_OAUTH_REDIRECT_URI", pre=True, always=True)
    def assemble_google_redirect_uri(cls, v: Optional[str], values: dict) -> str:
        if isinstance(v, str):
            return v
        public_api_url = values.get("PUBLIC_API_URL")
        return f"{public_api_url}/auth/callback/google"

    # --- RAG/LLM Settings ---
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    LLM_MODEL_NAME: str = "llama3-8b-8192"
    EMBEDDING_MODEL_NAME: str = "models/embedding-001"

    # --- Database Settings ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None

    @validator("DATABASE_URL", pre=True, always=True)
    def assemble_db_connection(cls, v: Optional[str], values: dict) -> str:
        if isinstance(v, str):
            return v
        return (
            f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}"
            f"@{values.get('POSTGRES_SERVER')}:{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"
        )

    # --- MinIO/S3 Settings ---
    MINIO_SERVER_URL: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_NAME: str = "documents"

    # --- JWT/Authentication Settings ---
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # --- Vector Store Path ---
    CHROMA_PATH: str = "/app/chroma_data"
    # --- Ollama ---
    OLLAMA_HOST: Optional[str] = None # <-- ADD THIS
    OLLAMA_MODEL: str = "phi3" # <-- ADD a default model

    # --- Celery ---
    CELERY_BROKER_URL: str

settings: Settings = Settings()