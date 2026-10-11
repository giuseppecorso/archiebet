"""Configurazione letta da backend/.env: nessun valore fisso nel codice (specifiche, sezione 14.6)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite:///data/archiebet.db"

    session_days: int = 30
    session_cookie_name: str = "archiebet_session"
    cookie_secure: bool = False

    data_cache_dir: Path = Path("data/cache")

    # API-Football: chiave, campionati (id) e stagioni (anno di inizio) da scaricare
    api_football_key: str | None = None
    api_football_leagues: str = "138,942,943"  # Serie C, gironi A, B, C
    api_football_seasons: str = "2022,2023,2024"  # quelle del piano gratuito
    api_football_daily_reserve: int = 10  # richieste del giorno da non usare mai in automatico

    # Aggiornamento automatico dei dati mentre il backend è acceso
    sync_enabled: bool = True
    sync_interval_hours: int = 6

    ai_monthly_budget_eur: float = 15.0
    ai_user_monthly_quota_eur: float = 10.0
    ai_budget_warning_ratio: float = 0.8

    @property
    def api_football_league_ids(self) -> list[int]:
        return [int(x) for x in self.api_football_leagues.split(",") if x.strip()]

    @property
    def api_football_season_years(self) -> list[int]:
        return [int(x) for x in self.api_football_seasons.split(",") if x.strip()]

    @field_validator("database_url")
    @classmethod
    def _sqlite_path_relative_to_backend(cls, url: str) -> str:
        # I percorsi SQLite relativi partono sempre da backend/, da qualunque cartella si avvii l'app
        prefix = "sqlite:///"
        if url.startswith(prefix) and url != "sqlite:///:memory:":
            path = Path(url.removeprefix(prefix))
            if not path.is_absolute():
                return prefix + (BACKEND_DIR / path).as_posix()
        return url

    @field_validator("data_cache_dir")
    @classmethod
    def _cache_dir_relative_to_backend(cls, path: Path) -> Path:
        return path if path.is_absolute() else BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
