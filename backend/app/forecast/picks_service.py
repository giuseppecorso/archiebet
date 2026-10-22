"""Pronostici delle partite in programma letti dal database (quote salvate e previsioni del modello)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.api_football import EAST_NORTH
from app.forecast.data import STATS_LEAGUES
from app.forecast.radar_markets import DNB
from app.forecast.multiple import Leg
from app.forecast.picks import MODEL_SOURCE, MarketPick, market_family, match_picks
from app.forecast.radar_service import load_book_odds
from app.forecast.review_service import apply_learning, current_state
from app.models import Competition, Match, MatchPrediction, MatchStatus


def upcoming_picks(db: Session, now: datetime, until: datetime, bookmakers: Sequence[str]) -> list[tuple[Match, list[MarketPick]]]:
    """Partite non ancora iniziate fino a `until`, ognuna con i suoi pronostici, in ordine di calcio d'inizio."""
    matches = list(
        db.scalars(
            select(Match)
            .join(Competition, Competition.id == Match.competition_id)
            .where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now, Match.kickoff_at <= until)
            .where(Competition.code.not_in(list(EAST_NORTH.values())))  # solo in Partite finché la prova D128 non passa
            .order_by(Match.kickoff_at, Match.id)
        )
    )
    ids = [m.id for m in matches]
    books = load_book_odds(db, ids, closing=False)
    models = {p.match_id: p.markets for p in db.scalars(select(MatchPrediction).where(MatchPrediction.match_id.in_(ids)))}
    state = current_state()
    return [(m, apply_learning(match_picks(books.get(m.id, {}), models.get(m.id), bookmakers, has_stats(m)), state)) for m in matches]


def has_stats(match: Match) -> bool:
    """Angoli e cartellini si chiudono solo dove arrivano le statistiche a fine partita (D131)."""
    return match.competition.code in STATS_LEAGUES


def match_market_picks(db: Session, match: Match, bookmakers: Sequence[str]) -> list[MarketPick]:
    """I Pronostici di una sola partita (pagina partita, D107)."""
    book = load_book_odds(db, [match.id], closing=False).get(match.id, {})
    prediction = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == match.id))
    return apply_learning(match_picks(book, prediction.markets if prediction else None, bookmakers, has_stats(match)), current_state())


def legs_for(picks: Sequence[tuple[Match, list[MarketPick]]], bookmaker: str, bench: frozenset[str] | None = None) -> list[Leg]:
    """Tutte le gambe giocabili su un bookmaker: ogni esito con la sua probabilità e la quota di quel bookmaker.
    I gruppi che Archie ha messo in panchina (D132) non entrano."""
    bench = current_state().bench if bench is None else bench
    legs = []
    for match, markets in picks:
        for mp in markets:
            if mp.source == MODEL_SOURCE or mp.market == DNB or f"{market_family(mp.market)} · {mp.source}" in bench:
                continue  # niente Draw No Bet nelle multiple: il rimborso col pareggio cambia i conti (D135)  # niente gambe dal solo modello (D88); il consenso dei bookmaker italiani sì (Serie C, D130)
            for selection, offers in mp.offers.items():
                for offer in offers:
                    if offer.bookmaker == bookmaker:
                        legs.append(Leg(match.id, match.kickoff_at, mp.market, selection, mp.probabilities[selection], offer.price, mp.source))
    return legs
