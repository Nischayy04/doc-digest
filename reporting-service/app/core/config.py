from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables / .env file.

    Note: no database_url here on purpose — reporting-service has no
    database access. It only ever talks to document-service over HTTP.
    See CLAUDE.md "Architecture" and LEARNING.md Phase 0 for why.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    service_name: str = "reporting-service"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    document_service_url: str = "http://localhost:8001"
    document_service_timeout_seconds: float = 10.0


settings = Settings()
