"""Lavori programmati: girano da soli mentre il backend è acceso."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.adapters.api_football import ApiFootballAdapter
from app.adapters.cache import FileCache
from app.adapters.football_data import FootballDataAdapter
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.ingest.api_football import sync_api_football
from app.ingest.football_data import sync_football_data
from app.usage import record_usage

logger = logging.getLogger("archiebet.jobs")


def sync_football_data_job() -> None:
    try:
        with SessionLocal() as db:
            adapter = FootballDataAdapter(
                FileCache(get_settings().data_cache_dir, "football-data"),
                on_call=lambda source: record_usage(db, source),
            )
            report = sync_football_data(db, adapter, log=logger.debug)
        logger.info("football-data aggiornato: %s nuove, %s aggiornate", report.created, report.updated)
    except Exception:
        logger.exception("Aggiornamento football-data non riuscito: riprovo al prossimo giro")


def api_football_adapter(db, settings: Settings) -> ApiFootballAdapter:
    return ApiFootballAdapter(
        FileCache(settings.data_cache_dir, "api-football"),
        settings.api_football_key,
        on_call=lambda source: record_usage(db, source),
        daily_reserve=settings.api_football_daily_reserve,
    )


def sync_api_football_job() -> None:
    settings = get_settings()
    if not settings.api_football_key:
        return
    try:
        with SessionLocal() as db:
            report = sync_api_football(
                db,
                api_football_adapter(db, settings),
                settings.api_football_league_ids,
                settings.api_football_season_years,
                log=logger.info,
            )
        logger.info("API-Football aggiornato: %s nuove, %s aggiornate", report.created, report.updated)
    except Exception:
        logger.exception("Aggiornamento API-Football non riuscito: riprovo al prossimo giro")


def sync_all_job() -> None:
    sync_football_data_job()
    sync_api_football_job()


def start_scheduler(settings: Settings) -> BackgroundScheduler | None:
    if not settings.sync_enabled:
        return None
    scheduler = BackgroundScheduler(timezone=UTC)
    scheduler.add_job(
        sync_all_job,
        "interval",
        hours=settings.sync_interval_hours,
        next_run_time=datetime.now(UTC) + timedelta(seconds=30),  # primo giro poco dopo l'avvio
        id="sync-data",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Aggiornamento automatico attivo ogni %s ore", settings.sync_interval_hours)
    return scheduler
