"""Bacheca Daily (D153): le schedine pubblicate da Archie, con le statistiche visibili a tutti."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.forecast.daily import KINDS, LOST, OPEN, ROME, WON, stats
from app.models import DailySlip, Match, MatchStatus

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
    from_market: bool | None = None  # pronostico costruito con le quote del mercato (None: schedine di prima)
    score: str | None = None  # risultato finale della partita, quando è finita


class DailySlipOut(BaseModel):
    id: int
    kind: str
    title: str
    period: str
    published_at: datetime
    singles: bool
    system: int | None = None  # sistema "k su n" (D157)
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


class SourceOut(BaseModel):
    """Pronostici chiusi dello studio, con e senza le quote del mercato: azzeccati, chiusi, attesi."""

    label: str
    won: int
    closed: int
    expected: float


class TodayOut(BaseModel):
    legs_won: int
    legs_closed: int
    legs_total: int


class DailyOut(BaseModel):
    board: list[DailySlipOut]  # l'ultima di ogni tipo
    today: TodayOut  # pronostici pubblicati oggi: azzeccati, chiusi, totali
    stats: list[KindStatsOut]
    history: list[DailySlipOut]  # le ultime chiuse
    by_source: list[SourceOut] = []


def _out(s: DailySlip, scores: dict[int, str] | None = None) -> DailySlipOut:
    k = KINDS[s.kind]
    scores = scores or {}
    return DailySlipOut(id=s.id, kind=s.kind, title=k.title, period=s.period, published_at=s.published_at, singles=k.singles, system=k.system,
                        legs=[DailyLegOut(**leg, score=scores.get(leg["match_id"])) for leg in s.legs], total_odds=s.total_odds, win_probability=s.win_probability, status=s.status)  # fmt: skip


@router.get("")
def daily(_: CurrentUser, db: DbSession) -> DailyOut:
    slips = list(db.scalars(select(DailySlip).order_by(DailySlip.published_at.desc(), DailySlip.id.desc())))
    today = datetime.now(UTC).astimezone(ROME).date().isoformat()
    board, seen = [], set()
    for s in slips:  # in bacheca l'ultima di ogni tipo, se è di oggi o ancora in corso; le altre vanno nell'archivio
        if s.kind not in seen:
            seen.add(s.kind)
            if s.period == today or s.status == OPEN:
                board.append(s)
    board.sort(key=lambda s: list(KINDS).index(s.kind))
    ids = {leg["match_id"] for s in slips for leg in s.legs}
    scores = {m.id: f"{m.home_goals}-{m.away_goals}" for m in db.scalars(select(Match).where(Match.id.in_(ids))) if m.home_goals is not None and m.status == MatchStatus.FINISHED}
    legs = [leg for s in slips if s.period == today for leg in s.legs]
    per_kind = stats(slips)
    return DailyOut(
        board=[_out(s, scores) for s in board],
        today=TodayOut(legs_won=sum(leg["status"] == WON for leg in legs), legs_closed=sum(leg["status"] in (WON, LOST) for leg in legs), legs_total=len(legs)),
        stats=[KindStatsOut(kind=k, title=KINDS[k].title, **vars(v)) for k, v in per_kind.items()],
        by_source=_by_source(slips),
        history=[_out(s, scores) for s in slips if s.status != OPEN and s not in board][:HISTORY],
    )


def _by_source(slips) -> list[SourceOut]:
    """Con le quote contro senza quote, sui pronostici dello studio già chiusi (da quando si registra la fonte)."""
    out = []
    for label, flag in (("Campionati con le quote", True), ("Campionati senza quote", False)):
        legs = [leg for s in slips for leg in s.legs if leg.get("from_market") is flag and leg["status"] in (WON, LOST)]
        out.append(SourceOut(label=label, won=sum(leg["status"] == WON for leg in legs), closed=len(legs), expected=round(sum(leg["p"] for leg in legs), 1)))
    return out
