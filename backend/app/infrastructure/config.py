from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "technical-document-search"
    database_url: str = "postgresql://app:app@localhost:5432/document_search"
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: str = "uploads"
    max_file_size_mb: int = 10
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    queue_name: str = "documents:processing"
    queue_group: str = "document-workers"
    dead_letter_queue: str = "documents:dead-letter"
    worker_max_attempts: int = 3
    worker_metrics_port: int = 9101
    max_batch_files: int = 20
    max_batch_size_mb: int = 50

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_batch_size_bytes(self) -> int:
        return self.max_batch_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
