"""Partite giocate e quote di riferimento lette dal database nel formato che serve al modello."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.football import Competition, Match, MatchOdds, MatchStatus


@dataclass(frozen=True)
class Game:
    match_id: int
    competition_id: int
    kickoff_at: datetime
    season: str
    tier: int  # 1 = Serie A, 2 = Serie B, 3 = Serie C
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


def load_games(db: Session) -> list[Game]:
    """Tutte le partite finite con risultato, in ordine di calcio d'inizio (a parità, per id)."""
    rows = db.execute(
        select(Match, Competition.tier)
        .join(Competition, Match.competition_id == Competition.id)
        .where(Match.status == MatchStatus.FINISHED, Match.home_goals.is_not(None), Match.away_goals.is_not(None))
        .order_by(Match.kickoff_at, Match.id)
    ).all()
    return [
        Game(m.id, m.competition_id, m.kickoff_at, m.season, tier, m.home_team_id, m.away_team_id, m.home_goals, m.away_goals)
        for m, tier in rows
    ]


# Riferimento di mercato per il confronto e il CLV (D48): Pinnacle di chiusura, altrimenti Betfair Exchange
REFERENCE_BOOKMAKERS = ("pinnacle", "betfair_ex")


def load_reference_closing_1x2(db: Session) -> dict[int, tuple[float, float, float]]:
    """Probabilità 1/X/2 "giuste" del mercato di chiusura, senza margine (metodo proporzionale)."""
    rows = db.execute(
        select(MatchOdds.match_id, MatchOdds.bookmaker, MatchOdds.selection, MatchOdds.price).where(
            MatchOdds.market == "1X2", MatchOdds.is_closing.is_(True), MatchOdds.bookmaker.in_(REFERENCE_BOOKMAKERS)
        )
    ).all()
    prices: dict[tuple[int, str], dict[str, float]] = {}
    for match_id, bookmaker, selection, price in rows:
        prices.setdefault((match_id, bookmaker), {})[selection] = float(price)
    out: dict[int, tuple[float, float, float]] = {}
    for bookmaker in reversed(REFERENCE_BOOKMAKERS):  # il primo della lista sovrascrive gli altri
        for (match_id, bm), p in prices.items():
            if bm == bookmaker and len(p) == 3 and all(v > 1 for v in p.values()):
                fair = fair_probabilities(p["1"], p["X"], p["2"])
                out[match_id] = fair
    return out


def fair_probabilities(*prices: float) -> tuple[float, ...]:
    """Toglie il margine del bookmaker: probabilità implicite (1/quota) riscalate a somma 1."""
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    return tuple(x / total for x in implied)
