from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "WDB Backend"

    # Datenbank
    sqlite_path: Path = Field(default=Path("data") / "wdb.sqlite3")

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3.2"
    ollama_timeout_seconds: int = 120
    ollama_enabled: bool = True

    # Neo4j (Phase 2 — optional)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_enabled: bool = False

    # Feature Flags
    neo4j_sync_enabled: bool = False  # Sync approved results → Neo4j

    supported_source_extensions: tuple[str, ...] = (".pdf", ".docx", ".txt", ".md", ".eml")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def async_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.sqlite_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
