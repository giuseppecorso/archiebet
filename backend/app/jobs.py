"""Lavori programmati: girano da soli mentre il backend è acceso."""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.adapters.cache import FileCache
from app.adapters.football_data import FootballDataAdapter
from app.config import Settings, get_settings
from app.db import SessionLocal
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


def start_scheduler(settings: Settings) -> BackgroundScheduler | None:
    if not settings.sync_enabled:
        return None
    scheduler = BackgroundScheduler(timezone=UTC)
    scheduler.add_job(
        sync_football_data_job,
        "interval",
        hours=settings.sync_interval_hours,
        next_run_time=datetime.now(UTC) + timedelta(seconds=30),  # primo giro poco dopo l'avvio
        id="sync-football-data",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Aggiornamento automatico attivo ogni %s ore", settings.sync_interval_hours)
    return scheduler
