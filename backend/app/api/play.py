"""Simulatore partita (Fase 6, D115). La sfida contro Archie (D116) è stata tolta (D126)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.football import MatchCard, match_cards
from app.auth.deps import CurrentUser, DbSession
from app.forecast.live_service import match_rates
from app.forecast.simulator import simulate
from app.models import Competition, Match, MatchStatus

router = APIRouter(prefix="/api/play", tags=["gioca"])

AHEAD = timedelta(days=7)


def _upcoming(db, competition: str | None = None) -> list[Match]:
    now = datetime.now(UTC)
    q = select(Match).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now, Match.kickoff_at <= now + AHEAD)
    if competition:
        q = q.join(Competition, Competition.id == Match.competition_id).where(Competition.code == competition)
    return list(db.scalars(q.order_by(Match.kickoff_at, Match.id)))


# ---------- Simulatore ----------



class GoalOut(BaseModel):
    minute: int
    side: str


class SimulationOut(BaseModel):
    match: MatchCard
    n: int
    minute: int
    score: tuple[int, int]
    rates: tuple[float, float]
    remaining: tuple[float, float]
    p_home: float
    p_draw: float
    p_away: float
    p_over25: float
    p_gg: float
    avg_goals: tuple[float, float]
    top_scores: list[tuple[int, int, float]]
    sample: list[GoalOut]


@router.get("/matches")
def sim_matches(_: CurrentUser, db: DbSession) -> list[MatchCard]:
    """Partite dei prossimi 7 giorni che si possono simulare (servono le probabilità prima della partita)."""
    matches = _upcoming(db)
    ok = match_rates(db, [m.id for m in matches])
    chosen = [m for m in matches if m.id in ok]
    return match_cards(db, chosen, datetime.now(UTC))


@router.get("/simulate")
def simulate_match(_: CurrentUser, db: DbSession, match_id: int, minute: int = Query(0, ge=0, le=90),
                   home: int = Query(0, ge=0, le=15), away: int = Query(0, ge=0, le=15)) -> SimulationOut:  # fmt: skip
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    rates = match_rates(db, [match_id]).get(match_id)
    if rates is None:
        raise HTTPException(422, "Per questa partita mancano le probabilità: non si può simulare")
    s = simulate(rates, minute, (home, away))
    [card] = match_cards(db, [match], datetime.now(UTC))
    return SimulationOut(match=card, n=s.n, minute=minute, score=(home, away), rates=s.rates, remaining=s.remaining, p_home=s.p_home, p_draw=s.p_draw,
                         p_away=s.p_away, p_over25=s.p_over25, p_gg=s.p_gg, avg_goals=s.avg_goals, top_scores=s.top_scores,
                         sample=[GoalOut(minute=e.minute, side=e.side) for e in s.sample])  # fmt: skip
