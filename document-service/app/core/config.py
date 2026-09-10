from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables / .env file.

    See LEARNING.md Phase 0 for why config is read from the environment
    instead of hardcoded.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    service_name: str = "document-service"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/documents"
    storage_dir: str = "./storage"
    max_upload_size_bytes: int = 20 * 1024 * 1024  # 20 MB


settings = Settings()
