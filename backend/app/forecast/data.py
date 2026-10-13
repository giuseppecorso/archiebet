"""Partite giocate e quote di riferimento lette dal database nel formato che serve al modello."""

from collections.abc import Sequence
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


# Il modello di Archie (Dixon-Coles + Elo collegati da promozioni e retrocessioni) è solo italiano:
# i campionati esteri servono per radar, statistiche e laboratorio; i loro modelli arrivano in Fase 8.
MODEL_COUNTRY = "Italia"


def load_games(db: Session, country: str = MODEL_COUNTRY) -> list[Game]:
    """Tutte le partite finite con risultato di un paese, in ordine di calcio d'inizio (a parità, per id)."""
    rows = db.execute(
        select(Match, Competition.tier)
        .join(Competition, Match.competition_id == Competition.id)
        .where(
            Competition.country == country,
            Match.status == MatchStatus.FINISHED,
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
        )
        .order_by(Match.kickoff_at, Match.id)
    ).all()
    return [
        Game(m.id, m.competition_id, m.kickoff_at, m.season, tier, m.home_team_id, m.away_team_id, m.home_goals, m.away_goals)
        for m, tier in rows
    ]


# Riferimento di mercato per il confronto e il CLV (D48): Pinnacle di chiusura, altrimenti Betfair Exchange
REFERENCE_BOOKMAKERS = ("pinnacle", "betfair_ex")
ODDS_MARKETS = {"1X2": ("1", "X", "2"), "OU2.5": ("over", "under")}

Odds = dict[int, dict[str, dict[str, float]]]  # partita → mercato → esito → quota


def load_odds(db: Session, bookmakers: Sequence[str], closing: bool) -> Odds:
    """Quote di ogni partita e mercato dal primo bookmaker disponibile nell'ordine dato.

    Un mercato si prende tutto dallo stesso bookmaker e solo se completo (tutti gli esiti, quote > 1).
    """
    rows = db.execute(
        select(MatchOdds.match_id, MatchOdds.bookmaker, MatchOdds.market, MatchOdds.selection, MatchOdds.price).where(
            MatchOdds.market.in_(ODDS_MARKETS), MatchOdds.is_closing.is_(closing), MatchOdds.bookmaker.in_(bookmakers)
        )
    ).all()
    found: dict[tuple[int, str, str], dict[str, float]] = {}
    for match_id, bookmaker, market, selection, price in rows:
        found.setdefault((match_id, market, bookmaker), {})[selection] = float(price)
    out: Odds = {}
    for bookmaker in reversed(bookmakers):  # il primo della lista sovrascrive gli altri
        for (match_id, market, bm), prices in found.items():
            if bm == bookmaker and set(prices) == set(ODDS_MARKETS[market]) and all(v > 1 for v in prices.values()):
                out.setdefault(match_id, {})[market] = prices
    return out


def fair_odds_probabilities(odds: Odds) -> Odds:
    """Le stesse quote trasformate in probabilità senza margine, mercato per mercato."""
    return {
        match_id: {market: dict(zip(prices, fair_probabilities(*prices.values()))) for market, prices in markets.items()}
        for match_id, markets in odds.items()
    }


def reference_1x2(fair: Odds) -> dict[int, tuple[float, float, float]]:
    """Solo l'1X2, come tupla (1, X, 2), per il confronto delle misure."""
    return {m: (v["1X2"]["1"], v["1X2"]["X"], v["1X2"]["2"]) for m, v in fair.items() if "1X2" in v}


def fair_probabilities(*prices: float) -> tuple[float, ...]:
    """Toglie il margine del bookmaker: probabilità implicite (1/quota) riscalate a somma 1."""
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    return tuple(x / total for x in implied)
