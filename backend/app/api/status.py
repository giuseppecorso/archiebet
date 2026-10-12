"""Stato dei dati: quanto sono freschi e pulsante "Aggiorna ora"."""

import threading
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.football import CompetitionOut, competition_out
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.jobs import is_syncing, sync_all_job
from app.models import Competition, Match, MatchPrediction, MatchStatus, SyncRun

router = APIRouter(prefix="/api/status", tags=["stato dei dati"])

SOURCES = [
    ("football-data", "Serie A e B: risultati e quote"),
    ("api-football", "Serie C: risultati e calendario"),
    ("predictions", "Previsioni di Archie"),
]


class SourceStatus(BaseModel):
    source: str
    label: str
    configured: bool
    last_ok_at: datetime | None  # ultimo aggiornamento riuscito
    last_run_at: datetime | None  # ultimo tentativo, riuscito o no
    last_run_ok: bool | None
    message: str | None


class CompetitionFreshness(BaseModel):
    competition: CompetitionOut
    last_result_at: datetime | None  # calcio d'inizio dell'ultimo risultato che abbiamo
    awaiting_results: int  # partite già giocate di cui non abbiamo ancora il risultato
    next_match_at: datetime | None


class StatusOut(BaseModel):
    now: datetime
    syncing: bool
    sources: list[SourceStatus]
    competitions: list[CompetitionFreshness]
    upcoming: int  # partite in programma non ancora iniziate
    upcoming_with_prediction: int


@router.get("")
def data_status(_: CurrentUser, db: DbSession) -> StatusOut:
    now = datetime.now(UTC)
    configured = {"football-data": True, "api-football": bool(get_settings().api_football_key), "predictions": True}
    sources = []
    for source, label in SOURCES:
        last = db.scalar(select(SyncRun).where(SyncRun.source == source).order_by(SyncRun.finished_at.desc()).limit(1))
        last_ok = db.scalar(select(func.max(SyncRun.finished_at)).where(SyncRun.source == source, SyncRun.ok.is_(True)))
        sources.append(
            SourceStatus(
                source=source,
                label=label,
                configured=configured[source],
                last_ok_at=last_ok,
                last_run_at=last.finished_at if last else None,
                last_run_ok=last.ok if last else None,
                message=last.message if last else None,
            )
        )

    competitions = []
    for c in db.scalars(select(Competition).order_by(Competition.tier, Competition.code)):
        in_comp = Match.competition_id == c.id
        competitions.append(
            CompetitionFreshness(
                competition=competition_out(c),
                last_result_at=db.scalar(select(func.max(Match.kickoff_at)).where(in_comp, Match.status == MatchStatus.FINISHED)),
                awaiting_results=db.scalar(
                    select(func.count()).where(in_comp, Match.status == MatchStatus.SCHEDULED, Match.kickoff_at < now)
                ),
                next_match_at=db.scalar(
                    select(func.min(Match.kickoff_at)).where(in_comp, Match.status == MatchStatus.SCHEDULED, Match.kickoff_at >= now)
                ),
            )
        )

    upcoming = select(Match.id).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now)
    return StatusOut(
        now=now,
        syncing=is_syncing(),
        sources=sources,
        competitions=competitions,
        upcoming=db.scalar(select(func.count()).select_from(upcoming.subquery())),
        upcoming_with_prediction=db.scalar(select(func.count()).where(MatchPrediction.match_id.in_(upcoming))),
    )


class RefreshOut(BaseModel):
    started: bool  # False se un aggiornamento era già in corso


@router.post("/refresh")
def refresh_now(_: CurrentUser) -> RefreshOut:
    """Avvia subito un aggiornamento completo in sottofondo (stesso lavoro di quello automatico)."""
    if is_syncing():
        return RefreshOut(started=False)
    threading.Thread(target=sync_all_job, name="aggiorna-ora", daemon=True).start()
    return RefreshOut(started=True)
