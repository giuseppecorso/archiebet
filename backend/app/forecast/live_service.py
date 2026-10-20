"""Dal database al termometro (D92): situazione live delle partite e probabilità delle giocate aperte."""

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forecast.live import LegState, bet_probability, fit_rates, leg_probability
from app.forecast.picks import best_probabilities
from app.forecast.radar_service import load_book_odds
from app.models import BetSelection, Match, MatchLive, MatchPrediction, MatchStatus

FRESH = timedelta(minutes=5)  # una riga live più vecchia di così non è più affidabile


def live_rows(db: Session, match_ids: Iterable[int], now: datetime) -> dict[int, MatchLive]:
    """Situazione live recente delle partite indicate (solo quelle non ancora finite)."""
    ids = list(match_ids)
    if not ids:
        return {}
    rows = db.scalars(select(MatchLive).where(MatchLive.match_id.in_(ids), MatchLive.updated_at >= now - FRESH))
    return {r.match_id: r for r in rows}


def match_rates(db: Session, match_ids: Sequence[int]) -> dict[int, tuple[float, float]]:
    """Gol attesi di casa e ospite dalle probabilità migliori prima della partita (Pinnacle → ... → modello)."""
    books = load_book_odds(db, list(match_ids), closing=False)
    models = {p.match_id: p.markets for p in db.scalars(select(MatchPrediction).where(MatchPrediction.match_id.in_(match_ids)))}
    out = {}
    for mid in match_ids:
        probs = best_probabilities(books.get(mid, {}), models.get(mid))
        if "1X2" not in probs:
            continue
        p = probs["1X2"][1]
        over = probs.get("OU2.5", (None, {}))[1].get("over")
        out[mid] = fit_rates(p["1"], p["2"], over)
    return out


def selection_states(db: Session, selections: Sequence[BetSelection], now: datetime) -> dict[int, LegState]:
    """Situazione di ogni gamba: chiusa (vinta/persa/annullata), in corso o da giocare."""
    match_ids = sorted({s.match_id for s in selections})
    live = live_rows(db, match_ids, now)
    rates = match_rates(db, [m for m in match_ids if any(s.match_id == m and s.status == "open" for s in selections)])
    out = {}
    for s in selections:
        m: Match = s.match
        settled = {"won": True, "void": True, "lost": False}.get(s.status)
        row = live.get(s.match_id)
        if row is not None and m.status != MatchStatus.FINISHED:
            out[s.id] = LegState(s.market, s.pick, rates.get(s.match_id), row.status, row.minute, row.home_goals, row.away_goals, settled)
        elif m.status == MatchStatus.FINISHED:
            out[s.id] = LegState(s.market, s.pick, rates.get(s.match_id), "FT", 90, m.home_goals or 0, m.away_goals or 0, settled)
        else:
            out[s.id] = LegState(s.market, s.pick, rates.get(s.match_id), "NS", None, 0, 0, settled)
    return out


def hope(states: Iterable[LegState]) -> float | None:
    return bet_probability(list(states))


__all__ = ["FRESH", "hope", "leg_probability", "live_rows", "match_rates", "selection_states"]
