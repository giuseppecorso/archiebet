"""Lavori programmati: girano da soli mentre il backend è acceso."""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.adapters.api_football import ApiFootballAdapter
from app.adapters.cache import FileCache
from app.adapters.football_data import FootballDataAdapter
from app.adapters.oddspapi import OddsPapiAdapter
from app.betting.service import settle_open_bets
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.forecast.radar_service import refresh_radar, settle_radar
from app.forecast.service import refresh_predictions
from app.ingest.api_football import sync_api_football
from app.ingest.football_data import sync_football_data
from app.ingest.oddspapi import sync_oddspapi
from app.models.sync import SyncRun
from app.usage import record_usage

logger = logging.getLogger("archiebet.jobs")

# Un solo aggiornamento alla volta (automatico o col pulsante "Aggiorna ora")
_sync_lock = threading.Lock()


def is_syncing() -> bool:
    return _sync_lock.locked()


def _tracked(source: str, work: Callable[[], str]) -> None:
    """Esegue un aggiornamento e lo scrive nel registro (sync_runs), riuscito o no."""
    started = datetime.now(UTC)
    try:
        message, ok = work(), True
    except Exception:
        logger.exception("Aggiornamento %s non riuscito: riprovo al prossimo giro", source)
        message, ok = "errore: riprovo al prossimo giro", False
    with SessionLocal() as db:
        db.add(SyncRun(source=source, started_at=started, finished_at=datetime.now(UTC), ok=ok, message=message[:200]))
        db.commit()


def sync_football_data_job() -> None:
    def work() -> str:
        with SessionLocal() as db:
            adapter = FootballDataAdapter(
                FileCache(get_settings().data_cache_dir, "football-data"),
                on_call=lambda source: record_usage(db, source),
            )
            report = sync_football_data(db, adapter, log=logger.debug)
        logger.info("football-data aggiornato: %s nuove, %s aggiornate", report.created, report.updated)
        return f"{report.created} partite nuove, {report.updated} aggiornate"

    _tracked("football-data", work)


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

    def work() -> str:
        with SessionLocal() as db:
            report = sync_api_football(
                db,
                api_football_adapter(db, settings),
                settings.api_football_league_ids,
                settings.api_football_season_years,
                log=logger.info,
            )
        logger.info("API-Football aggiornato: %s nuove, %s aggiornate", report.created, report.updated)
        return f"{report.created} partite nuove, {report.updated} aggiornate"

    _tracked("api-football", work)


def sync_oddspapi_job() -> None:
    settings = get_settings()
    if not settings.oddspapi_key:
        return

    def work() -> str:
        with SessionLocal() as db:
            adapter = OddsPapiAdapter(
                FileCache(settings.data_cache_dir, "oddspapi"),
                settings.oddspapi_key,
                on_call=lambda source: record_usage(db, source),
                monthly_reserve=settings.oddspapi_monthly_reserve,
            )
            report = sync_oddspapi(db, adapter, datetime.now(UTC), log=logger.warning, bookmakers=settings.radar_bookmaker_list)
        message = f"quote di {report.current} partite, {report.closing} chiusure"
        if report.not_in_calendar:
            message += f", {report.not_in_calendar} partite non ancora in calendario"
        if adapter.remaining_month is not None:
            message += f" · restano {adapter.remaining_month} richieste nel mese"
        logger.info("OddsPapi: %s", message)
        return message

    _tracked("oddspapi", work)


def settle_bets_job() -> None:
    try:
        with SessionLocal() as db:
            closed = settle_open_bets(db)
        if closed:
            logger.info("Schedine chiuse automaticamente: %s", closed)
    except Exception:
        logger.exception("Chiusura automatica delle schedine non riuscita")


def refresh_predictions_job() -> None:
    def work() -> str:
        with SessionLocal() as db:
            updated = refresh_predictions(db, datetime.now(UTC))
        if updated:
            logger.info("Previsioni di Archie aggiornate: %s partite", updated)
        return f"{updated} partite ricalcolate" if updated else "nessun dato nuovo, previsioni già aggiornate"

    _tracked("predictions", work)


def refresh_radar_job() -> None:
    def work() -> str:
        with SessionLocal() as db:
            settled = settle_radar(db)  # prima si misurano i segnali delle partite finite
            found = refresh_radar(db, datetime.now(UTC), get_settings().radar_bookmaker_list)
        if found or settled:
            logger.info("Radar: %s segnali nuovi, %s misurati con la chiusura", found, settled)
        return f"{found} segnali nuovi, {settled} misurati con la chiusura"

    _tracked("radar", work)


def sync_all_job() -> bool:
    """Aggiorna tutto. Se un aggiornamento è già in corso non ne parte un secondo (restituisce False)."""
    if not _sync_lock.acquire(blocking=False):
        logger.info("Aggiornamento già in corso: salto")
        return False
    try:
        sync_football_data_job()
        sync_api_football_job()
        sync_oddspapi_job()  # dopo il calendario: le quote si agganciano alle partite che abbiamo
        settle_bets_job()  # dopo i risultati nuovi
        refresh_predictions_job()  # si ricalcola solo se sono arrivati dati nuovi
        refresh_radar_job()  # dopo le quote nuove
        return True
    finally:
        _sync_lock.release()


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
