"""Gioca (Fase 6, solo crediti finti): simulatore partita (D115) e sfida contro Archie (D116)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.football import MatchCard, match_cards
from app.auth.deps import CurrentUser, DbSession
from app.betting.challenge import STAKE, Settled, archie_pick, outcome, score
from app.forecast.live_service import match_rates
from app.forecast.picks import best_probabilities
from app.forecast.radar_service import load_book_odds
from app.forecast.simulator import simulate
from app.models import ChallengePick, Competition, Match, MatchPrediction, MatchStatus, User

router = APIRouter(prefix="/api/play", tags=["gioca"])

AHEAD = timedelta(days=7)


def _upcoming(db, competition: str | None = None) -> list[Match]:
    now = datetime.now(UTC)
    q = select(Match).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now, Match.kickoff_at <= now + AHEAD)
    if competition:
        q = q.join(Competition, Competition.id == Match.competition_id).where(Competition.code == competition)
    return list(db.scalars(q.order_by(Match.kickoff_at, Match.id)))


def _probs_1x2(db, matches: list[Match]) -> dict[int, dict[str, float]]:
    ids = [m.id for m in matches]
    books = load_book_odds(db, ids, closing=False)
    models = {p.match_id: p.markets for p in db.scalars(select(MatchPrediction).where(MatchPrediction.match_id.in_(ids)))}
    out = {}
    for m in matches:
        p = best_probabilities(books.get(m.id, {}), models.get(m.id)).get("1X2")
        if p:
            out[m.id] = p[1]
    return out


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


# ---------- Sfida contro Archie ----------


class ChallengeRow(BaseModel):
    match: MatchCard
    probabilities: dict[str, float] | None
    fair_odds: dict[str, float] | None
    my_pick: str | None
    archie_pick: str | None
    open: bool  # si può ancora scegliere (prima del calcio d'inizio)
    credits: float | None  # a partita finita


class Standing(BaseModel):
    name: str
    picks: int
    correct: int
    hit_rate: float | None
    credits: float


class ChallengeOut(BaseModel):
    stake: float
    rows: list[ChallengeRow]
    standings: list[Standing]


class PickIn(BaseModel):
    match_id: int
    selection: str


def _settled(picks: list[ChallengePick], archie: bool = False) -> list[Settled]:
    out = []
    for p in picks:
        m = p.match
        if m.status == MatchStatus.FINISHED and m.home_goals is not None and m.away_goals is not None:
            sel, odds = (p.archie_selection, p.archie_fair_odds) if archie else (p.selection, p.fair_odds)
            out.append(Settled(sel, float(odds), outcome(m.home_goals, m.away_goals)))
    return out


@router.get("/challenge")
def challenge(user: CurrentUser, db: DbSession, competition: str = "ITA-A") -> ChallengeOut:
    matches = _upcoming(db, competition)
    probs = _probs_1x2(db, matches)
    mine = {p.match_id: p for p in db.scalars(select(ChallengePick).where(ChallengePick.user_id == user.id))}
    # Le partite giocate di recente con un pronostico restano in elenco con il risultato
    recent = [p.match for p in mine.values() if p.match.kickoff_at > datetime.now(UTC) - timedelta(days=10) and p.match.id not in {m.id for m in matches}]
    shown = sorted(recent, key=lambda m: m.kickoff_at, reverse=True) + matches
    cards = {c.id: c for c in match_cards(db, shown, datetime.now(UTC))}
    now = datetime.now(UTC)
    rows = []
    for m in shown:
        p = probs.get(m.id)
        pick = mine.get(m.id)
        settled = _settled([pick]) if pick else []
        rows.append(ChallengeRow(match=cards[m.id], probabilities=p, fair_odds={k: 1 / v for k, v in p.items()} if p else None,
                                 my_pick=pick.selection if pick else None, archie_pick=pick.archie_selection if pick else (archie_pick(p) if p else None),
                                 open=m.status == MatchStatus.SCHEDULED and m.kickoff_at > now,
                                 credits=score(settled).credits if settled else None))  # fmt: skip
    all_picks = list(db.scalars(select(ChallengePick)))
    standings = []
    for u in db.scalars(select(User)):
        s = score(_settled([p for p in all_picks if p.user_id == u.id]))
        if s.picks:
            standings.append(Standing(name=u.username, picks=s.picks, correct=s.correct, hit_rate=s.hit_rate, credits=s.credits))
    a = score(_settled([p for p in all_picks if p.user_id == user.id], archie=True))
    if a.picks:
        standings.append(Standing(name="Archie", picks=a.picks, correct=a.correct, hit_rate=a.hit_rate, credits=a.credits))
    standings.sort(key=lambda s: -s.credits)
    return ChallengeOut(stake=STAKE, rows=rows, standings=standings)


@router.post("/challenge")
def make_pick(body: PickIn, user: CurrentUser, db: DbSession) -> dict:
    if body.selection not in ("1", "X", "2"):
        raise HTTPException(422, "Scegli 1, X o 2")
    match = db.get(Match, body.match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    if match.status != MatchStatus.SCHEDULED or match.kickoff_at <= datetime.now(UTC):
        raise HTTPException(409, "La partita è già iniziata")
    p = _probs_1x2(db, [match]).get(match.id)
    if p is None:
        raise HTTPException(422, "Per questa partita mancano le probabilità")
    pick = db.scalar(select(ChallengePick).where(ChallengePick.user_id == user.id, ChallengePick.match_id == match.id))
    archie = archie_pick(p)
    if pick is None:
        pick = ChallengePick(user_id=user.id, match_id=match.id)
        db.add(pick)
    pick.selection, pick.fair_odds = body.selection, Decimal(str(round(1 / p[body.selection], 3)))
    pick.archie_selection, pick.archie_fair_odds = archie, Decimal(str(round(1 / p[archie], 3)))
    db.commit()
    return {"ok": True}
