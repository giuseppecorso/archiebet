"""Pagella settimanale di Archie (D132): righe ricostruite dall'archivio delle quote, salvataggio e stato attuale.

Le righe vengono dall'archivio OddsPapi (storia dei prezzi di Pinnacle, Sisal ed Eurobet) collegato alle partite
finite del database; le correzioni attive si applicano ai Pronostici e al generatore di multiple.
"""

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.adapters.oddspapi import TOURNAMENTS, OPFixture, parse_history, prices_at
from app.config import get_settings
from app.forecast.data import STATS_LEAGUES
from app.forecast.learning_service import learning_dir
from app.forecast.picks import MarketPick, Offer, best_probabilities, match_picks, price_verdict
from app.forecast.radar_markets import is_secondary, is_team_goals, secondary_won
from app.forecast.radar_service import won
from app.forecast.review import Row, State, recalibrate, snapshot_time, weekly_report
from app.models import Match, MatchStatus

REVIEW_BOOKMAKERS = ("sisal", "eurobet")
REVIEW_FILE = "review.json"


def winners_of(market: str, selections: Sequence[str], match: Match) -> frozenset[str] | None:
    """Esiti vinti di un mercato; None se servono angoli o cartellini e le statistiche non ci sono.
    Draw No Bet col pareggio: nessun esito vinto (puntata restituita)."""
    if market == "DNB" or is_team_goals(market):
        from app.betting.calc import WON, selection_outcome

        return frozenset(s for s in selections if selection_outcome(market, s, match.home_goals, match.away_goals) == WON)
    if is_secondary(market):
        stats = ((match.home_corners, match.away_corners), (match.home_yellow, match.away_yellow), (match.home_red or 0, match.away_red or 0))
        outcome = {s: secondary_won(market, s, *stats) for s in selections}
        return None if None in outcome.values() else frozenset(s for s, hit in outcome.items() if hit)
    return frozenset(s for s in selections if won(match.home_goals, match.away_goals, market, s))


def rows_for(record: dict[str, Any], match: Match, secondary_map: dict) -> list[Row]:
    """I mercati di una partita archiviata: stima di Archie alla foto delle 10, chiusura ed esito."""
    history = parse_history(record, secondary_map)
    kickoff = match.kickoff_at if match.kickoff_at.tzinfo else match.kickoff_at.replace(tzinfo=UTC)
    with_stats = match.competition.code in STATS_LEAGUES
    book = prices_at(history, snapshot_time(kickoff))
    closing = best_probabilities(prices_at(history, kickoff), None, with_stats)
    rows = []
    for mp in match_picks(book, None, REVIEW_BOOKMAKERS, with_stats):
        prices = {bm: {s: book[bm][mp.market][s] for s in mp.probabilities if s in book.get(bm, {}).get(mp.market, {})} for bm in REVIEW_BOOKMAKERS}
        rows.append(Row(
            match.id, kickoff, match.competition.code, mp.market, mp.source, mp.probabilities,
            winners_of(mp.market, list(mp.probabilities), match),
            closing[mp.market][1] if mp.market in closing else None,
            {bm: p for bm, p in prices.items() if p},
        ))  # fmt: skip
    return rows


def load_rows(db, log=print) -> list[Row]:
    """Tutte le righe dall'archivio delle quote (campionati con calendario nel database, partite finite)."""
    from app.adapters.cache import FileCache
    from app.adapters.oddspapi import OddsPapiAdapter
    from app.ingest.oddspapi import OddsPapiReport, link_fixtures

    settings = get_settings()
    adapter = OddsPapiAdapter(FileCache(settings.data_cache_dir, "oddspapi"), settings.oddspapi_key)
    records = []
    for path in (settings.data_cache_dir / "odds-archive").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))["data"]
        if data.get("bookmakers") and data["fixture"].get("tournamentId") in TOURNAMENTS:
            records.append(data)
    fixtures = [OPFixture(r["fixture"]["fixtureId"], r["fixture"]["tournamentId"], datetime.fromisoformat(r["fixture"]["startTime"].replace("Z", "+00:00")),
                          r["fixture"]["participant1Id"], r["fixture"]["participant2Id"], 2) for r in records]  # fmt: skip
    names = {str(r["fixture"][f"participant{k}Id"]): r["fixture"][f"participant{k}Name"] for r in records for k in (1, 2)}
    links = link_fixtures(db, fixtures, adapter.participants() | names, OddsPapiReport(), datetime.now(UTC))
    db.commit()
    secondary_map = adapter.secondary_markets()
    rows: list[Row] = []
    for r, fx in zip(records, fixtures):
        match = links.get(fx.id)
        if match is None or match.status != MatchStatus.FINISHED or match.home_goals is None:
            continue
        rows.extend(rows_for(r, match, secondary_map))
    log(f"pagella: {len(records)} partite in archivio, {len({r.match_id for r in rows})} con risultato, {len(rows)} mercati")
    return rows


def review_path() -> Path:
    return learning_dir() / REVIEW_FILE


def study_scorecard(db) -> dict:
    """Per ogni partita finita con uno studio, il pronostico migliore di ogni livello (quello che la multipla avrebbe
    proposto) confrontato con il risultato."""
    from sqlalchemy import select

    from app.betting.calc import WON, needs_half_time, selection_outcome
    from app.forecast.review import day_of, week_of
    from app.forecast.study import LEVELS, pick_strength, scorecard
    from app.models import MatchStudy

    rows = []
    for m, study in db.execute(select(Match, MatchStudy).join(MatchStudy, MatchStudy.match_id == Match.id)
                               .where(Match.status == MatchStatus.FINISHED, Match.home_goals.is_not(None))).all():  # fmt: skip
        kickoff = m.kickoff_at if m.kickoff_at.tzinfo else m.kickoff_at.replace(tzinfo=UTC)
        ht = (m.ht_home_goals, m.ht_away_goals) if m.ht_home_goals is not None else None
        for level in LEVELS:
            mine = [p for p in study.data["picks"] if p["level"] == level]
            if not mine:
                continue
            best = max(mine, key=pick_strength)
            if needs_half_time(best["market"]) and ht is None:
                continue
            hit = selection_outcome(best["market"], best["selection"], m.home_goals, m.away_goals, ht) == WON
            rows.append((week_of(day_of(kickoff)).isoformat(), level, best["p_archie"], hit))
    return scorecard(rows)


def refresh_review(log=print) -> str:
    """Rifà la pagella di tutte le settimane e aggiorna correzioni e panchina (lavoro settimanale)."""
    from app.db import SessionLocal

    with SessionLocal() as db:
        rows = load_rows(db, log)
    report = weekly_report(rows, REVIEW_BOOKMAKERS)
    with SessionLocal() as db:
        report["study"] = study_scorecard(db)  # pronostici studiati: usciti contro promessi (D139)
    report["computed_at"] = datetime.now(UTC).isoformat()
    review_path().write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    load_review.cache_clear()
    state = report["state"]
    return f"pagella: {len(report['weeks'])} settimane; tarature attive {len(state['corrections'])}, in panchina {len(state['bench'])}"


@lru_cache(maxsize=1)
def load_review() -> dict | None:
    path = review_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def current_state() -> State:
    """Le correzioni che Archie usa adesso (dall'ultima pagella)."""
    state = (load_review() or {}).get("state") or {}
    corrections = {g: (c["a"], c["b"]) for g, c in (state.get("corrections") or {}).items()}
    return State(corrections, frozenset(state.get("bench") or ()))


def apply_learning(picks: Sequence[MarketPick], state: State) -> list[MarketPick]:
    """Pronostici con le tarature attive: probabilità corrette, valore ed etichetta delle quote ricalcolati."""
    if not state.corrections:
        return list(picks)
    from app.forecast.picks import double_chance, market_family

    out, fixed_1x2 = [], None
    for mp in picks:
        params = state.corrections.get(f"{market_family(mp.market)} · {mp.source}")
        if mp.market == "DC" and fixed_1x2 is not None:
            probs = double_chance(fixed_1x2)
        elif params is not None and mp.market != "DC":
            probs = recalibrate(mp.probabilities, *params)
            if mp.market == "1X2":
                fixed_1x2 = probs
        else:
            out.append(mp)
            continue
        offers = {
            s: [Offer(o.bookmaker, o.price, v := probs[s] * o.price - 1, price_verdict(v, o.price, mp.source)) for o in os]
            for s, os in mp.offers.items()
        }
        out.append(replace(mp, probabilities=probs, offers=offers, corrected=True))
    return out
