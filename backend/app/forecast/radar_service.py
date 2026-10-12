"""Radar sulle partite in programma e simulazione dal vivo (D57, D59), salvati per partita (sezione 14.2).

- refresh_radar: dopo ogni aggiornamento delle quote cerca i segnali nelle partite non ancora iniziate.
  La prima volta che un esito ha valore diventa una giocata simulata (quota e valore non cambiano più).
- settle_radar: quando arrivano le quote di chiusura calcola il CLV di ogni segnale (il giudice, principio 2).
"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forecast.clv import ClvSummary
from app.forecast.data import ODDS_MARKETS
from app.forecast.radar import (
    FALLBACK_BOOKMAKERS,
    PLAYABLE_BOOKMAKERS,
    RADAR_THRESHOLD,
    BookOdds,
    closing_value,
    fair_reference,
    scan,
    summarize_live,
)
from app.models.football import Match, MatchOdds, MatchStatus
from app.models.forecast import RadarSignal


PREFERRED_SOURCE = "oddspapi"  # quote più fresche: se lo stesso bookmaker arriva da due fonti, vince questa


def load_book_odds(db: Session, match_ids: Iterable[int], closing: bool) -> dict[int, BookOdds]:
    """Quote di tutti i bookmaker, partita per partita, solo per i mercati del radar.

    Un mercato si prende tutto da una fonte sola: OddsPapi se c'è, altrimenti l'altra (es. Pinnacle di football-data).
    """
    ids = list(match_ids)
    found: dict[tuple[int, str, str], dict[str, dict[str, float]]] = {}  # (partita, bookmaker, mercato) → fonte → quote
    for start in range(0, len(ids), 500):
        rows = db.execute(
            select(MatchOdds.match_id, MatchOdds.source, MatchOdds.bookmaker, MatchOdds.market, MatchOdds.selection, MatchOdds.price).where(
                MatchOdds.match_id.in_(ids[start : start + 500]),
                MatchOdds.market.in_(ODDS_MARKETS),
                MatchOdds.is_closing.is_(closing),
            )
        ).all()
        for match_id, source, bookmaker, market, selection, price in rows:
            found.setdefault((match_id, bookmaker, market), {}).setdefault(source, {})[selection] = float(price)
    out: dict[int, BookOdds] = {}
    for (match_id, bookmaker, market), by_source in found.items():
        prices = by_source.get(PREFERRED_SOURCE) or next(iter(by_source.values()))
        out.setdefault(match_id, {}).setdefault(bookmaker, {})[market] = prices
    return out


def playable_for(book: BookOdds) -> tuple[str, ...]:
    """Bookmaker italiani se la partita ne ha le quote, altrimenti il ripiego di football-data."""
    return PLAYABLE_BOOKMAKERS if any(bm in book for bm in PLAYABLE_BOOKMAKERS) else FALLBACK_BOOKMAKERS


def refresh_radar(db: Session, now: datetime) -> int:
    """Aggiorna i segnali delle partite non ancora iniziate. Restituisce quanti segnali nuovi ha trovato."""
    upcoming = list(db.scalars(select(Match.id).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now)))
    if not upcoming:
        return 0
    books = load_book_odds(db, upcoming, closing=False)
    existing = {
        (s.match_id, s.market, s.selection): s
        for s in db.scalars(select(RadarSignal).where(RadarSignal.match_id.in_(upcoming)))
    }
    created = 0
    for match_id in upcoming:
        # Tutti gli esiti, anche senza valore: servono a seguire i segnali già visti
        book = books.get(match_id, {})
        current = {(c.market, c.selection): c for c in scan(book, threshold=float("-inf"), playable=playable_for(book))}
        for (m, market, selection), row in existing.items():
            if m == match_id and (market, selection) not in current:  # quota sparita
                row.latest_bookmaker = row.latest_price = row.latest_value = None
                row.checked_at = now
        for (market, selection), c in current.items():
            row = existing.get((match_id, market, selection))
            if row is None:
                if c.value < RADAR_THRESHOLD:
                    continue
                row = RadarSignal(
                    match_id=match_id, market=market, selection=selection, detected_at=now, bookmaker=c.bookmaker,
                    price=c.price, fair_probability=round(c.fair_probability, 5), fair_source=c.fair_source,
                    value=round(c.value, 5),
                )
                db.add(row)
                created += 1
            row.checked_at = now
            row.latest_bookmaker, row.latest_price, row.latest_value = c.bookmaker, c.price, round(c.value, 5)
    db.commit()
    return created


def _won(match: Match, market: str, selection: str) -> bool:
    if market == "1X2":
        h, a = match.home_goals, match.away_goals
        return selection == ("1" if h > a else "X" if h == a else "2")
    return (match.home_goals + match.away_goals >= 3) == (selection == "over")


def settle_radar(db: Session) -> int:
    """Calcola CLV (con la chiusura di D48) ed esito dei segnali delle partite finite. Restituisce quanti ne ha chiusi."""
    rows = db.execute(
        select(RadarSignal, Match)
        .join(Match, RadarSignal.match_id == Match.id)
        .where(RadarSignal.clv.is_(None), Match.status == MatchStatus.FINISHED)
    ).all()
    if not rows:
        return 0
    closing = load_book_odds(db, {s.match_id for s, _ in rows}, closing=True)
    settled = 0
    for signal, match in rows:
        if match.home_goals is not None and match.away_goals is not None:
            signal.won = _won(match, signal.market, signal.selection)
        ref = fair_reference(closing.get(signal.match_id, {}), signal.market)
        if ref is None:  # chiusura non ancora disponibile: si riprova al prossimo aggiornamento
            continue
        source, fair = ref
        signal.closing_source = source
        signal.closing_fair_probability = round(fair[signal.selection], 5)
        signal.clv = round(closing_value(signal.price, fair[signal.selection]), 5)
        settled += 1
    db.commit()
    return settled


def live_summary(db: Session) -> ClvSummary | None:
    """Riepilogo della simulazione dal vivo sui segnali già misurati con la chiusura."""
    signals = list(db.scalars(select(RadarSignal).where(RadarSignal.clv.is_not(None))))
    clv = [s.clv for s in signals]
    profit = [s.price - 1.0 if s.won else -1.0 for s in signals if s.won is not None]
    return summarize_live(clv, profit)
