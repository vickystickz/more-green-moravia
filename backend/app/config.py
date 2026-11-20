"""Settings from the environment (and backend/.env)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    APP_NAME: str = "More Green, Moravia API"

    # Model: any OpenAI-compatible chat-completions API
    AI_BASE_URL: str | None = None
    AI_API_KEY: str | None = None
    AI_MODEL: str | None = None
    AI_TIMEOUT_SECONDS: float = 60

    AGENT_MAX_STEPS: int = 6
    AGENT_MAX_CONCURRENT: int = 4

    # Data: the GeoJSON exports are loaded into this DuckDB file. The exports
    # are copies of the frontend's files in frontend/data/, kept in backend/data/
    # so the backend (and its Docker image) needs nothing outside backend/.
    DUCKDB_PATH: Path = Path("data/moravia.duckdb")
    INDEX_GEOJSON: Path = Path("data/olomouc_gi_h3_r9.geojson")
    INDEX_METADATA: Path = Path("data/olomouc_gi_h3_r9_metadata.json")
    MICROZONES_GEOJSON: Path = Path("data/olomouc_microzones.geojson")

    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    # Also allowed: any localhost port, so the site can be served on its own
    # port while this API uses 8000. Set to "" to turn off.
    CORS_ORIGIN_REGEX: str = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

    @property
    def agent_configured(self) -> bool:
        return bool(self.AI_BASE_URL and self.AI_MODEL)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def path(self, value: Path) -> Path:
        """Relative paths are relative to backend/, wherever the server is started."""
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()


settings = Settings()
