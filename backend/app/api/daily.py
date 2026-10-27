"""Bacheca Daily (D153): le schedine pubblicate da Archie, con le statistiche visibili a tutti."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.forecast.daily import KINDS, LOST, OPEN, ROME, WON, stats
from app.models import DailySlip

router = APIRouter(prefix="/api/daily", tags=["daily"])
HISTORY = 30


class DailyLegOut(BaseModel):
    match_id: int
    kickoff_at: datetime
    competition: str
    home: str
    away: str
    market: str
    selection: str
    event: str  # il pronostico detto a parole
    p: float  # probabilità di Archie (per il CLV: quella giusta di Pinnacle)
    price: float  # quota al momento della pubblicazione
    status: str  # open | won | lost | void


class DailySlipOut(BaseModel):
    id: int
    kind: str
    title: str
    period: str
    published_at: datetime
    singles: bool
    legs: list[DailyLegOut]
    total_odds: float
    win_probability: float
    status: str


class KindStatsOut(BaseModel):
    kind: str
    title: str
    published: int
    closed: int
    won: int
    expected: float
    legs_won: int
    legs_closed: int
    profit: float


class TodayOut(BaseModel):
    legs_won: int
    legs_closed: int
    legs_total: int


class DailyOut(BaseModel):
    board: list[DailySlipOut]  # l'ultima di ogni tipo
    today: TodayOut  # pronostici pubblicati oggi: azzeccati, chiusi, totali
    stats: list[KindStatsOut]
    history: list[DailySlipOut]  # le ultime chiuse


def _out(s: DailySlip) -> DailySlipOut:
    k = KINDS[s.kind]
    return DailySlipOut(id=s.id, kind=s.kind, title=k.title, period=s.period, published_at=s.published_at, singles=k.singles,
                        legs=[DailyLegOut(**leg) for leg in s.legs], total_odds=s.total_odds, win_probability=s.win_probability, status=s.status)  # fmt: skip


@router.get("")
def daily(_: CurrentUser, db: DbSession) -> DailyOut:
    slips = list(db.scalars(select(DailySlip).order_by(DailySlip.published_at.desc(), DailySlip.id.desc())))
    board, seen = [], set()
    for s in slips:
        if s.kind not in seen:
            seen.add(s.kind)
            board.append(s)
    board.sort(key=lambda s: list(KINDS).index(s.kind))
    today = datetime.now(UTC).astimezone(ROME).date().isoformat()
    legs = [leg for s in slips if s.period == today for leg in s.legs]
    per_kind = stats(slips)
    return DailyOut(
        board=[_out(s) for s in board],
        today=TodayOut(legs_won=sum(leg["status"] == WON for leg in legs), legs_closed=sum(leg["status"] in (WON, LOST) for leg in legs), legs_total=len(legs)),
        stats=[KindStatsOut(kind=k, title=KINDS[k].title, **vars(v)) for k, v in per_kind.items()],
        history=[_out(s) for s in slips if s.status != OPEN][:HISTORY],
    )
