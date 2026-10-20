"""Radar delle quote: segnali sulle partite in programma e simulazione dal vivo (D57, D59, D63)."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.football import BOOKMAKER_LABELS, CompetitionOut, TeamRef, competition_out
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.forecast.clv import SUSPICIOUS_VALUE
from app.forecast.radar_markets import is_secondary
from app.forecast.radar import LIVE_TARGET, MAX_PRICE, RADAR_THRESHOLD, SIMULATION_BOOKMAKERS, live_verdict, qualifies, required_value, scan
from app.forecast.radar_service import live_summary, load_book_odds
from app.models import Match, MatchStatus, RadarSignal

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
    latest_is_occasion: bool  # la quota di adesso è ancora un'occasione (regola D72)?
    clv: float | None
    won: bool | None
    secondary: bool = False  # angoli o cartellini: simulazione e verdetto separati (D94)


class OccasionOut(BaseModel):
    """Occasione di adesso su un bookmaker di Giuse (calcolata al momento, non salvata)."""

    match_id: int
    competition: CompetitionOut
    kickoff_at: datetime
    home: TeamRef
    away: TeamRef
    market: str
    selection: str
    bookmaker: str
    price: float
    fair_probability: float
    fair_source: str
    value: float
    required_value: float  # soglia per quella quota (D72)
    suspicious: bool
    secondary: bool = False  # angoli o cartellini, "in prova" (D94)


class LiveOut(BaseModel):
    n: int
    target: int
    mean_clv: float | None
    clv_std_error: float | None
    share_positive: float | None
    roi: float | None
    verdict: str  # "in prova" | "superato" | "non superato"


class RadarOut(BaseModel):
    threshold: float  # valore minimo a quota 2 (la soglia cresce con la quota, D72)
    max_price: float
    playable: list[str]  # i bookmaker di Giuse: le occasioni mostrate
    simulation_bookmakers: list[str]  # quelli su cui si misura la simulazione (D74)
    upcoming: list[OccasionOut]
    recent: list[SignalOut]
    live: LiveOut
    live_secondary: LiveOut  # simulazione di angoli e cartellini su Sisal ed Eurobet (D94)


def _live_out(summary) -> LiveOut:
    return LiveOut(
        n=summary.n if summary else 0,
        target=LIVE_TARGET,
        mean_clv=summary.mean_clv if summary else None,
        clv_std_error=summary.clv_std_error if summary and summary.n > 1 else None,
        share_positive=summary.share_positive if summary else None,
        roi=summary.roi if summary else None,
        verdict=live_verdict(summary),
    )


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
        latest_is_occasion=s.latest_price is not None and s.latest_value is not None and qualifies(s.latest_price, s.latest_value),
        clv=s.clv,
        won=s.won,
        secondary=is_secondary(s.market),
    )


@router.get("")
def radar(_: CurrentUser, db: DbSession) -> RadarOut:
    now = datetime.now(UTC)
    playable = get_settings().radar_bookmaker_list
    matches = list(db.scalars(
        select(Match).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now).order_by(Match.kickoff_at, Match.id)
    ))  # fmt: skip
    books = load_book_odds(db, [m.id for m in matches], closing=False)
    upcoming = [
        OccasionOut(
            match_id=m.id, competition=competition_out(m.competition), kickoff_at=m.kickoff_at,
            home=TeamRef(id=m.home_team.id, name=m.home_team.name), away=TeamRef(id=m.away_team.id, name=m.away_team.name),
            market=c.market, selection=c.selection, bookmaker=_label(c.bookmaker), price=c.price,
            fair_probability=c.fair_probability, fair_source=_label(c.fair_source), value=c.value,
            required_value=required_value(c.price), suspicious=c.suspicious, secondary=is_secondary(c.market),
        )
        for m in matches
        for c in scan(books.get(m.id, {}), playable=playable)
    ]  # fmt: skip
    recent = db.execute(
        select(RadarSignal, Match).join(Match, RadarSignal.match_id == Match.id)
        .where(Match.kickoff_at <= now).order_by(Match.kickoff_at.desc(), RadarSignal.id).limit(RECENT_LIMIT)
    ).all()  # fmt: skip
    summary = live_summary(db)
    return RadarOut(
        threshold=RADAR_THRESHOLD,
        max_price=MAX_PRICE,
        playable=[_label(b) for b in playable],
        simulation_bookmakers=[_label(b) for b in SIMULATION_BOOKMAKERS],
        upcoming=upcoming,
        recent=[_signal_out(s, m) for s, m in recent],
        live=_live_out(summary),
        live_secondary=_live_out(live_summary(db, secondary=True)),
    )
