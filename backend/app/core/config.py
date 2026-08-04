from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ruta del fichero `.env` situado en la raíz del repositorio.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Configuración de la aplicación, leída de variables de entorno o `.env`."""

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    max_file_size_mb: int = 15
    max_image_bytes: int = 18 * 1024 * 1024
    cors_origins: str = "http://localhost:4200"
    temperature: float = 0.0

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
