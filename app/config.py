from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # DATABASE_URL and database_url are treated the same
        extra="ignore",         # silently ignore unknown vars in .env
    )

    APP_NAME: str = "Loan Document Review"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    LOG_LEVEL: str = "INFO"

    # Accepts a JSON array or a comma-separated string in .env:
    #   CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]
    #   CORS_ORIGINS=http://localhost:3000,http://localhost:8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Required — no default. Must use the asyncpg driver scheme:
    #   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/loan_rag
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # "ollama" for local dev; "bedrock" for production (no EC2 required).
    LLM_PROVIDER: Literal["ollama", "bedrock"] = "ollama"

    # Ollama (local dev)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3.2"

    # Amazon Bedrock (production)
    BEDROCK_MODEL_ID: str = "amazon.nova-lite-v1:0"
    BEDROCK_REGION: str = "us-east-2"

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def validate_log_level(cls, v: Any) -> str:
        normalised = str(v).upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalised not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(valid)}, got '{v}'")
        return normalised

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        raise ValueError(
            "CORS_ORIGINS must be a JSON array or a comma-separated string"
        )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> str:
        url = str(v)
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the 'postgresql+asyncpg://' scheme. "
                "Example: postgresql+asyncpg://user:password@localhost:5432/loan_rag"
            )
        return url

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def log_level_int(self) -> int:
        return logging.getLevelName(self.LOG_LEVEL)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
