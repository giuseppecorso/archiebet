"""Radar delle quote: segnali sulle partite in programma e simulazione dal vivo (D57, D59, D63)."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.football import BOOKMAKER_LABELS, CompetitionOut, TeamRef, competition_out
from app.auth.deps import CurrentUser, DbSession
from app.forecast.clv import SUSPICIOUS_VALUE
from app.forecast.radar import LIVE_TARGET, PLAYABLE_BOOKMAKERS, RADAR_THRESHOLD, live_verdict
from app.forecast.radar_service import live_summary
from app.models import Match, RadarSignal

router = APIRouter(prefix="/api/radar", tags=["radar"])

RECENT_LIMIT = 30


class SignalOut(BaseModel):
    match_id: int
    competition: CompetitionOut
    kickoff_at: datetime
    home: TeamRef
    away: TeamRef
    market: str
    selection: str
    detected_at: datetime
    bookmaker: str  # etichetta: dove giocarla (prima rilevazione = giocata simulata)
    price: float
    fair_probability: float
    fair_source: str
    value: float
    suspicious: bool
    latest_bookmaker: str | None  # le quote di adesso (None = quota sparita)
    latest_price: float | None
    latest_value: float | None
    clv: float | None
    won: bool | None


class LiveOut(BaseModel):
    n: int
    target: int
    mean_clv: float | None
    clv_std_error: float | None
    share_positive: float | None
    roi: float | None
    verdict: str  # "in prova" | "superato" | "non superato"


class RadarOut(BaseModel):
    threshold: float
    playable: list[str]
    upcoming: list[SignalOut]
    recent: list[SignalOut]
    live: LiveOut


def _label(bookmaker: str | None) -> str | None:
    return BOOKMAKER_LABELS.get(bookmaker, bookmaker) if bookmaker else None


def _signal_out(s: RadarSignal, m: Match) -> SignalOut:
    return SignalOut(
        match_id=m.id,
        competition=competition_out(m.competition),
        kickoff_at=m.kickoff_at,
        home=TeamRef(id=m.home_team.id, name=m.home_team.name),
        away=TeamRef(id=m.away_team.id, name=m.away_team.name),
        market=s.market,
        selection=s.selection,
        detected_at=s.detected_at,
        bookmaker=_label(s.bookmaker),
        price=s.price,
        fair_probability=s.fair_probability,
        fair_source=_label(s.fair_source),
        value=s.value,
        suspicious=s.value > SUSPICIOUS_VALUE,
        latest_bookmaker=_label(s.latest_bookmaker),
        latest_price=s.latest_price,
        latest_value=s.latest_value,
        clv=s.clv,
        won=s.won,
    )


@router.get("")
def radar(_: CurrentUser, db: DbSession) -> RadarOut:
    now = datetime.now(UTC)
    upcoming = db.execute(
        select(RadarSignal, Match).join(Match, RadarSignal.match_id == Match.id)
        .where(Match.kickoff_at > now).order_by(Match.kickoff_at, RadarSignal.value.desc())
    ).all()  # fmt: skip
    recent = db.execute(
        select(RadarSignal, Match).join(Match, RadarSignal.match_id == Match.id)
        .where(Match.kickoff_at <= now).order_by(Match.kickoff_at.desc(), RadarSignal.id).limit(RECENT_LIMIT)
    ).all()  # fmt: skip
    summary = live_summary(db)
    return RadarOut(
        threshold=RADAR_THRESHOLD,
        playable=[BOOKMAKER_LABELS.get(b, b) for b in PLAYABLE_BOOKMAKERS],
        upcoming=[_signal_out(s, m) for s, m in upcoming],
        recent=[_signal_out(s, m) for s, m in recent],
        live=LiveOut(
            n=summary.n if summary else 0,
            target=LIVE_TARGET,
            mean_clv=summary.mean_clv if summary else None,
            clv_std_error=summary.clv_std_error if summary and summary.n > 1 else None,
            share_positive=summary.share_positive if summary else None,
            roi=summary.roi if summary else None,
            verdict=live_verdict(summary),
        ),
    )
