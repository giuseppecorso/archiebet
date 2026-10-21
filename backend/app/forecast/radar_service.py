"""Radar sulle partite in programma e simulazione dal vivo (D57, D59), salvati per partita (sezione 14.2).

- refresh_radar: dopo ogni aggiornamento delle quote cerca i segnali nelle partite non ancora iniziate.
  La prima volta che un esito ha valore diventa una giocata simulata (quota e valore non cambiano più).
- settle_radar: quando arrivano le quote di chiusura calcola il CLV di ogni segnale (il giudice, principio 2).
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.forecast.clv import ClvSummary
from app.forecast.data import EXTRA_GOAL_MARKETS, ODDS_MARKETS, OVERLAPPING_MARKETS
from app.forecast.radar_markets import is_secondary, secondary_won
from app.forecast.radar import (
    PLAYABLE_BOOKMAKERS,
    qualifies,
    BookOdds,
    closing_value,
    fair_reference,
    scan,
    summarize_live,
)
from app.forecast.strategy_search import Fixture, Strategy, matching, season_moments
from app.models.football import Competition, Match, MatchOdds, MatchStatus
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
                or_(MatchOdds.market.in_([*ODDS_MARKETS, *OVERLAPPING_MARKETS, *EXTRA_GOAL_MARKETS]), MatchOdds.market.like("COR%"), MatchOdds.market.like("CRD%")),
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


def strategy_context(db: Session, upcoming: Sequence[int]) -> tuple[dict[int, str], dict[int, str | None]]:
    """Campionato e momento della stagione delle partite in arrivo, per le strategie di Archie (D118)."""
    codes = dict(db.execute(select(Competition.id, Competition.code)).all())
    rows = db.execute(select(Match.id, Match.competition_id, Match.season).where(Match.id.in_(upcoming))).all()
    league = {mid: codes[cid] for mid, cid, _ in rows}
    seasons = {(cid, season) for _, cid, season in rows}
    same_season = or_(*(and_(Match.competition_id == cid, Match.season == season) for cid, season in seasons))
    fixtures = [Fixture(m.id, codes[m.competition_id], m.season, m.kickoff_at, m.home_team_id, m.away_team_id)
                for m in db.scalars(select(Match).where(same_season))]  # fmt: skip
    return league, season_moments(fixtures)


def refresh_radar(db: Session, now: datetime, playable: Sequence[str] = PLAYABLE_BOOKMAKERS,
                  strategies: Sequence[Strategy] = ()) -> int:  # fmt: skip
    """Aggiorna i segnali delle partite non ancora iniziate (solo sui bookmaker giocabili). Restituisce quanti segnali nuovi.

    Oltre alla regola D72, un esito diventa occasione se lo gioca una strategia trovata da Archie e confermata (D118).
    """
    upcoming = list(db.scalars(select(Match.id).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now)))
    if not upcoming:
        return 0
    league, moments = strategy_context(db, upcoming) if strategies else ({}, {})
    books = load_book_odds(db, upcoming, closing=False)
    existing = {
        (s.match_id, s.market, s.selection): s
        for s in db.scalars(select(RadarSignal).where(RadarSignal.match_id.in_(upcoming)))
    }
    created = 0
    for match_id in upcoming:
        # Tutti gli esiti, anche senza valore: servono a seguire i segnali già visti
        book = books.get(match_id, {})
        current = {(c.market, c.selection): c for c in scan(book, playable=playable, all_outcomes=True)}
        for (m, market, selection), row in existing.items():
            if m == match_id and (market, selection) not in current:  # quota sparita
                row.latest_bookmaker = row.latest_price = row.latest_value = None
                row.checked_at = now
        for (market, selection), c in current.items():
            row = existing.get((match_id, market, selection))
            if row is None:
                found = matching(strategies, league.get(match_id, ""), market, selection, c.price, c.value, moments.get(match_id)) if strategies else None
                if not qualifies(c.price, c.value) and found is None:
                    continue
                row = RadarSignal(
                    match_id=match_id, market=market, selection=selection, detected_at=now, bookmaker=c.bookmaker,
                    price=c.price, fair_probability=round(c.fair_probability, 5), fair_source=c.fair_source,
                    value=round(c.value, 5), strategy=found.name[:200] if found else None,
                )
                db.add(row)
                created += 1
            row.checked_at = now
            row.latest_bookmaker, row.latest_price, row.latest_value = c.bookmaker, c.price, round(c.value, 5)
    db.commit()
    return created


def won(home_goals: int, away_goals: int, market: str, selection: str) -> bool:
    """L'esito si è verificato? (1X2, doppia chance, Under/Over 2.5, Goal/NoGoal)"""
    outcome = "1" if home_goals > away_goals else "X" if home_goals == away_goals else "2"
    if market == "1X2":
        return selection == outcome
    if market == "DC":
        return outcome in selection
    if market == "GG":
        return (home_goals > 0 and away_goals > 0) == (selection == "yes")
    if market.startswith("OU"):
        return (home_goals + away_goals > float(market[2:])) == (selection == "over")
    raise ValueError(f"Mercato sconosciuto: {market}")


def settle_radar(db: Session, now: datetime | None = None) -> int:
    """Misura i segnali: CLV appena c'è la chiusura (dopo il calcio d'inizio, anche senza risultato), esito col risultato.

    Il CLV non aspetta il risultato: football-data lo pubblica anche settimane dopo. Restituisce i CLV nuovi.
    """
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(RadarSignal, Match)
        .join(Match, RadarSignal.match_id == Match.id)
        .where(
            Match.status != MatchStatus.CANCELLED,
            or_(
                and_(RadarSignal.clv.is_(None), Match.kickoff_at < now),
                and_(RadarSignal.won.is_(None), Match.status == MatchStatus.FINISHED),
            ),
        )
    ).all()
    if not rows:
        return 0
    closing = load_book_odds(db, {s.match_id for s, _ in rows}, closing=True)
    settled = 0
    for signal, match in rows:
        if match.status == MatchStatus.FINISHED and match.home_goals is not None and match.away_goals is not None:
            if is_secondary(signal.market):  # angoli e cartellini: servono i dati della partita (football-data)
                signal.won = secondary_won(signal.market, signal.selection, (match.home_corners, match.away_corners),
                                           (match.home_yellow, match.away_yellow), (match.home_red, match.away_red))
            else:
                signal.won = won(match.home_goals, match.away_goals, signal.market, signal.selection)
        if signal.clv is not None:
            continue
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


def live_summary(db: Session, secondary: bool = False) -> ClvSummary | None:
    """Riepilogo della simulazione dal vivo sui segnali già misurati con la chiusura.

    secondary=False: mercati principali (verdetto D59); True: angoli e cartellini (verdetto separato D94), con
    l'errore standard per partita perché più linee della stessa partita non sono indipendenti.
    """
    signals = [s for s in db.scalars(select(RadarSignal).where(RadarSignal.clv.is_not(None))) if is_secondary(s.market) == secondary]
    clv = [s.clv for s in signals]
    profit = [s.price - 1.0 if s.won else -1.0 for s in signals if s.won is not None]
    summary = summarize_live(clv, profit)
    if summary is None or not secondary:
        return summary
    from app.forecast.history_sim import clustered_mean

    est = clustered_mean(clv, [s.match_id for s in signals])
    return ClvSummary(summary.n, summary.mean_clv, est.std_error, summary.share_positive, summary.roi)
