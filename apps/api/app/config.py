"""Pydantic Settings — loads from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres
    DATABASE_URL: str = "postgresql+asyncpg://vajra:vajra@localhost:5432/vajratrace"

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "vajratrace"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # API keys
    ETHERSCAN_API_KEY: str = ""
    TRONGRID_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""  # kept for backward compat; not used

    # Groq (OpenAI-compatible LLM)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"


settings = Settings()
