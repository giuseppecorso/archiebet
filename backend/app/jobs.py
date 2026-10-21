"""Lavori programmati: girano da soli mentre il backend è acceso."""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.adapters.api_football import ApiFootballAdapter
from app.adapters.cache import FileCache
from app.adapters.football_data import FootballDataAdapter, season_of
from app.adapters.oddspapi import OddsPapiAdapter
from app.betting.service import settle_open_bets
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.forecast.learning_service import passed_strategies, refresh_learning
from app.forecast.radar import SIMULATION_BOOKMAKERS
from app.forecast.radar_service import refresh_radar, settle_radar
from app.forecast.service import refresh_predictions
from app.ingest.api_football import sync_api_football
from app.ingest.football_data import ImportReport, sync_football_data
from app.ingest.live import needs_live, sync_live
from app.ingest.news import run_news
from app.ingest.odds_archive import archive_history
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
            report = sync_football_data(db, adapter, log=logger.debug, skip_imported=True)
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


def sync_api_football_all(db, settings: Settings, log=logger.info) -> ImportReport:
    """Serie C con lo storico; tutti i campionati per la stagione in corso (D80)."""
    adapter = api_football_adapter(db, settings)
    current = season_of(datetime.now(UTC).date())
    past = [s for s in settings.api_football_season_years if s < current]
    report = sync_api_football(db, adapter, settings.api_football_league_ids, past, log=log)
    leagues = [*settings.api_football_league_ids, *settings.api_football_current_league_ids]
    report.add(sync_api_football(db, adapter, leagues, [current], log=log))
    return report


def sync_api_football_job() -> None:
    settings = get_settings()
    if not settings.api_football_key:
        return

    def work() -> str:
        with SessionLocal() as db:
            report = sync_api_football_all(db, settings)
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
            # Quote dei bookmaker di Giuse e di quelli della simulazione (D74), senza doppioni
            bookmakers = list(dict.fromkeys([*settings.radar_bookmaker_list, *SIMULATION_BOOKMAKERS]))
            report = sync_oddspapi(db, adapter, datetime.now(UTC), log=logger.warning, bookmakers=bookmakers)
        # Gli storici completi pesano fino a 20 MB l'uno e si riscaricano gratis: si tengono 2 giorni
        adapter.cache.prune("historical-odds", timedelta(days=2))
        message = f"{report.created} partite in calendario, quote di {report.current} partite, {report.closing} chiusure"
        if report.not_in_calendar:
            message += f", {report.not_in_calendar} partite già iniziate non aggiunte"
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
            settled = settle_radar(db, datetime.now(UTC))  # prima si misurano i segnali delle partite iniziate
            found = refresh_radar(db, datetime.now(UTC), SIMULATION_BOOKMAKERS, passed_strategies())  # 8 bookmaker (D74) + strategie D118
        if found or settled:
            logger.info("Radar: %s segnali nuovi, %s misurati con la chiusura", found, settled)
        return f"{found} segnali nuovi, {settled} misurati con la chiusura"

    _tracked("radar", work)


def archive_job() -> None:
    """Ogni settimana: storico quote delle ultime 3 settimane di Serie C e campionati principali (prove D98 e D119).

    Lo storico è gratuito; costa una richiesta per campionato o girone (13 a settimana, ~56 al mese sulle 250).
    """
    settings = get_settings()
    if not settings.oddspapi_key:
        return

    def work() -> str:
        with SessionLocal() as db:
            adapter = OddsPapiAdapter(FileCache(settings.data_cache_dir, "oddspapi"), settings.oddspapi_key,
                                      on_call=lambda source: record_usage(db, source), monthly_reserve=settings.oddspapi_monthly_reserve)
            report = archive_history(adapter, FileCache(settings.data_cache_dir, "odds-archive"), datetime.now(UTC) - timedelta(days=21),
                                     log=logger.debug)  # fmt: skip
        return f"archivio quote: {report.saved} salvate, {report.missing} senza storico, {report.already} già presenti"

    _tracked("oddspapi", work)


def learning_job() -> None:
    """Ogni settimana, dopo l'archivio: Archie rifà da solo le prove della Fase 7 (strategie, quando giocare, taratura)."""

    def work() -> str:
        return refresh_learning(log=logger.debug)

    _tracked("learning", work)


def news_job() -> None:
    """Ogni 2 ore: Archie tifoso (D101-D102). Notizie, fatti, giudizi, chiusure; senza chiave Claude solo raccolta."""
    from app.adapters.news import NewsAdapter
    from app.ai.client import Ai

    settings = get_settings()

    def work() -> str:
        now = datetime.now(UTC)
        with SessionLocal() as db:
            ai = Ai(db, settings.anthropic_api_key, settings) if settings.anthropic_api_key else None
            report = run_news(db, NewsAdapter(FileCache(settings.data_cache_dir, "news")), ai, settings.ai_extract_model, settings.ai_model, now)
        for error in report.errors:
            logger.warning("Notizie: %s", error)
        return (f"{report.new} notizie nuove, {report.facts} fatti da {report.processed} lette, {report.judged} partite giudicate,"
                f" {report.settled} chiusure")  # fmt: skip

    _tracked("news", work)


def player_stats_job() -> None:
    """Ogni 12 ore: statistiche di squadre e giocatori delle partite nuove di Serie A e B (D111)."""
    from app.adapters.football_data import season_of
    from app.ingest.af_stats import STATS_LEAGUES, download_match_stats

    settings = get_settings()
    if not settings.api_football_key:
        return

    def work() -> str:
        with SessionLocal() as db:
            report = download_match_stats(api_football_adapter(db, settings), STATS_LEAGUES, [season_of(datetime.now(UTC).date())], log=logger.debug)
        return f"statistiche giocatori: {report.done} partite in cache su {report.fixtures}" + (f" ({report.stopped})" if report.stopped else "")

    _tracked("api-football", work)


_live_lock = threading.Lock()


def live_job() -> None:
    """Ogni minuto: se una nostra partita è in corso, minuto e punteggio; a fine partita risultato e schedine (D92).

    Non si scrive nel registro degli aggiornamenti (sarebbe una riga al minuto): gli errori vanno nel log.
    """
    settings = get_settings()
    if not settings.api_football_key or not _live_lock.acquire(blocking=False):
        return
    try:
        now = datetime.now(UTC)
        with SessionLocal() as db:
            if not needs_live(db, now):
                return
            leagues = [*settings.api_football_league_ids, *settings.api_football_current_league_ids]
            report = sync_live(db, api_football_adapter(db, settings), leagues, now)
            if report.finished:
                settle_radar(db, now)
        if report.finished:
            settle_bets_job()
            logger.info("Live: %s partite finite, schedine aggiornate", report.finished)
    except Exception:
        logger.exception("Aggiornamento live non riuscito: riprovo tra un minuto")
    finally:
        _live_lock.release()


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
    scheduler.add_job(live_job, "interval", seconds=60, id="live", max_instances=1, coalesce=True)
    scheduler.add_job(archive_job, "interval", days=7, next_run_time=datetime.now(UTC) + timedelta(minutes=30),
                      id="odds-archive", max_instances=1, coalesce=True)  # fmt: skip
    scheduler.add_job(learning_job, "interval", days=7, next_run_time=datetime.now(UTC) + timedelta(hours=2),
                      id="learning", max_instances=1, coalesce=True)  # fmt: skip
    scheduler.add_job(player_stats_job, "interval", hours=12, next_run_time=datetime.now(UTC) + timedelta(minutes=20),
                      id="player-stats", max_instances=1, coalesce=True)  # fmt: skip
    scheduler.add_job(news_job, "interval", hours=2, next_run_time=datetime.now(UTC) + timedelta(minutes=3),
                      id="news", max_instances=1, coalesce=True)  # fmt: skip
    scheduler.start()
    logger.info("Aggiornamento automatico attivo ogni %s ore", settings.sync_interval_hours)
    return scheduler
