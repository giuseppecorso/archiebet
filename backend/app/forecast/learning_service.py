"""Cosa impara Archie (Fase 7, D117-D121): dati storici e prove ripetute da solo ogni settimana.

Archie rifà le prove pre-registrate (strategie D118, quando giocare D119, taratura D120) e salva i risultati in un
file: la scheda "Cosa impara Archie" del Laboratorio li mostra, le Occasioni usano le strategie che passano.
"""

import json
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.adapters.oddspapi import MARKETS, TOURNAMENTS
from app.config import get_settings
from app.db import SessionLocal
from app.forecast import history_sim as hs
from app.forecast import strategy_search as ss
from app.forecast import timing as tm
from app.forecast.data import load_odds
from app.forecast.demargin import shin
from app.ingest.odds_archive import EAST_NORTH_TOURNAMENTS, MINOR_TOURNAMENTS
from app.models import Competition, Match, MatchStatus

ROME = ZoneInfo("Europe/Rome")
HISTORY_LEAGUES = ("ITA-A", "ITA-B", "ENG-1", "ENG-2", "ESP-1", "ESP-2", "GER-1", "GER-2", "FRA-1", "FRA-2")
TIMING_GROUPS = {"ITA-A": "Serie A e B", "ITA-B": "Serie A e B", "ITA-C-A": "Serie C", "ITA-C-B": "Serie C", "ITA-C-C": "Serie C"}
STRATEGY_FIRST = "2012/13"
STRATEGY_SPLIT = "2020/21"  # prima stagione di conferma (D118)
LAST = "9999/99"  # tutte le stagioni presenti
CALIBRATION_MATCHES = 2000  # taratura controllata sulle 2.000 partite più recenti di ogni gruppo (D120)


# --- Dati ---------------------------------------------------------------------------------------------------


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_timing_books() -> list[tm.Book]:
    """Storia delle quote dall'archivio OddsPapi, per la prova D119 (solo partite finite, coppe escluse)."""
    codes = {**TOURNAMENTS, **MINOR_TOURNAMENTS, **EAST_NORTH_TOURNAMENTS}
    books = []
    for path in (get_settings().data_cache_dir / "odds-archive").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))["data"]
        fx = record["fixture"]
        code = codes.get(fx.get("tournamentId"))
        if code is None or code.startswith("EU-") or not record.get("bookmakers"):
            continue
        tid = fx["tournamentId"]
        group = TIMING_GROUPS.get(code) or ("serie minori" if tid in MINOR_TOURNAMENTS else "est e nord" if tid in EAST_NORTH_TOURNAMENTS else "estero")
        prices: dict = {}
        for slug, book in record["bookmakers"].items():
            for market_id, market in (book.get("markets") or {}).items():
                if market_id not in MARKETS or MARKETS[market_id][0] not in tm.SELECTIONS:
                    continue
                name, outcomes = MARKETS[market_id]
                for oid, outcome in (market.get("outcomes") or {}).items():
                    if oid in outcomes:
                        points = [(_ts(p["createdAt"]), float(p["price"]) if p.get("active", True) and p.get("price") else None)
                                  for p in (outcome.get("players") or {}).get("0") or []]  # fmt: skip
                        prices.setdefault(slug.split(".")[0], {}).setdefault(name, {})[outcomes[oid]] = sorted(points, key=lambda x: x[0])
        books.append(tm.Book(fx["fixtureId"], group, _ts(fx["startTime"]), prices))
    return books


def sim_matches(first: str, last: str, bookmakers: Sequence[str] = ("bet365",)) -> tuple[dict[str, list[hs.SimMatch]], list[ss.Fixture]]:
    """Partite storiche con Pinnacle d'apertura e chiusura (Shin) e la quota d'apertura di ogni bookmaker indicato (D86),
    più il calendario completo (squadre) per il momento della stagione."""

    def fair(prices):
        return {market: dict(zip(sel, shin(list(sel.values())))) for market, sel in prices.items() if market in ("1X2", "OU2.5")}

    with SessionLocal() as db:
        matches = db.execute(
            select(Match).join(Competition, Match.competition_id == Competition.id)
            .where(Competition.code.in_(HISTORY_LEAGUES), Match.season >= first, Match.season <= last)
        ).scalars().all()  # fmt: skip
        fixtures = [ss.Fixture(m.id, m.competition.code, m.season, m.kickoff_at, m.home_team_id, m.away_team_id) for m in matches]
        info = {m.id: (m.season, m.competition.code, m.kickoff_at, m.home_goals, m.away_goals) for m in matches if m.status == MatchStatus.FINISHED}
        pin_open = load_odds(db, ["pinnacle"], closing=False)
        pin_close = load_odds(db, ["pinnacle"], closing=True)
        books = {name: load_odds(db, [name], closing=False) for name in bookmakers}

    def build(book):
        out = []
        for mid, (season, league, kickoff, hg, ag) in info.items():
            if mid not in pin_open or mid not in pin_close or mid not in book or hg is None:
                continue
            out.append(hs.SimMatch(mid, season, league, kickoff.astimezone(ROME).date(), kickoff, hg, ag, fair(pin_open[mid]),
                                   fair(pin_close[mid]), {k: v for k, v in book[mid].items() if k in ("1X2", "OU2.5")}))
        return out

    return {name: build(book) for name, book in books.items()}, fixtures


# --- Rapporti -----------------------------------------------------------------------------------------------


def _est(e: hs.Estimate | None) -> dict | None:
    return None if e is None else {"mean": e.mean, "se": e.std_error if math.isfinite(e.std_error) else None, "n": e.n}


def strategy_dict(s: ss.Strategy) -> dict:
    return {"league": s.league, "market": s.market, "selection": s.selection, "band": list(s.band), "moment": s.moment,
            "filter": s.filter, "name": s.name}  # fmt: skip


def strategy_from(d: dict) -> ss.Strategy:
    return ss.Strategy(d["league"], d["market"], d["selection"], (d["band"][0], d["band"][1]), d["moment"], d["filter"])


def strategy_report(sims: Sequence[hs.SimMatch], fixtures: Sequence[ss.Fixture]) -> dict:
    """Ricerca D118 sulle stagioni presenti: taratura prima del 2020/21, conferma dal 2020/21 in poi."""
    items = ss.bets(sims, ss.season_moments(fixtures))
    tuning = [b for b in items if b.season < STRATEGY_SPLIT]
    confirm = [b for b in items if b.season >= STRATEGY_SPLIT]
    strategies = ss.all_strategies(HISTORY_LEAGUES)
    results = ss.search(strategies, tuning, confirm)

    def row(r: ss.Result) -> dict:
        return {"strategy": strategy_dict(r.strategy), "tuning": _est(r.tuning_clv), "tuning_roi": _est(r.tuning_roi),
                "confirm": _est(r.confirm_clv), "confirm_roi": _est(r.confirm_roi), "candidate": r.candidate, "passed": r.passed}  # fmt: skip

    valid = [r for r in results if r.tuning_n >= ss.MIN_PLAYS and r.tuning_clv]
    closest = sorted(valid, key=lambda r: -r.tuning_clv.t)[:5]
    return {
        "tested": len(strategies),
        "tuning_bets": len(tuning),
        "confirm_bets": len(confirm),
        "tuning_seasons": [STRATEGY_FIRST, max((b.season for b in tuning), default=None)],
        "confirm_seasons": [STRATEGY_SPLIT, max((b.season for b in confirm), default=None)],
        "candidates": [row(r) for r in results if r.candidate],
        "passed": [row(r) for r in results if r.passed],
        "closest": [row(r) for r in closest],
    }


def timing_report(books: Sequence[tm.Book]) -> dict:
    obs = tm.observations(books, lambda b: "consensus" if b.group == "Serie C" else "pinnacle")
    groups = []
    for group in ("Serie A e B", "Serie C", "estero", "est e nord", "serie minori"):
        sel = [o for o in obs if o.group == group]
        if not sel:
            continue
        advice = tm.advise(sel)
        occasions = []
        if group != "Serie C":
            for h in tm.OCCASION_HORIZONS:
                t = tm.occasion_timing(sel, h)
                if t:
                    occasions.append({"horizon": h, "n": t.n, "now": _est(t.now), "gain": _est(t.gain), "still_value": t.still_value, "play_now": t.play_now})
        groups.append({
            "group": group, "matches": len({o.fixture_id for o in sel}), "verdict": advice.verdict, "best": advice.best,
            "horizons": [{"label": r.label, "clv": _est(r.clv), "vs_last": _est(r.vs_last)} for r in advice.results],
            "occasions": occasions,
        })  # fmt: skip
    return {"matches": len(books), "groups": groups}


def calibration_report(sims: Sequence[hs.SimMatch]) -> dict:
    """D120: taratura delle probabilità giuste (Pinnacle d'apertura, Shin) sulle partite più recenti, per gruppo e mercato.
    Una fascia è "fuori taratura" se la frequenza vera si allontana dalla prevista oltre 2 errori standard."""
    out = []
    for group, leagues in (("Serie A e B", ("ITA-A", "ITA-B")), ("estero", tuple(c for c in HISTORY_LEAGUES if not c.startswith("ITA")))):
        chosen = sorted((m for m in sims if m.league in leagues), key=lambda m: m.kickoff)[-CALIBRATION_MATCHES:]
        for market in ("1X2", "OU2.5"):
            bins = hs.calibration(chosen, market)
            out.append({
                "group": group, "market": market, "matches": len(chosen),
                "since": chosen[0].day.isoformat() if chosen else None, "until": chosen[-1].day.isoformat() if chosen else None,
                "bins": [{"low": b.low, "high": b.high, "n": b.n, "predicted": b.predicted, "observed": b.observed, "se": b.std_error,
                          "off": abs(b.off_by) > 2 * b.std_error} for b in bins],
            })  # fmt: skip
    return {"matches_per_group": CALIBRATION_MATCHES, "rows": out}


MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


def value_map(sims: Sequence[hs.SimMatch]) -> dict:
    """Mappa del valore: Occasioni D72 (alla quota bet365 d'apertura) per campionato e mese, con il loro CLV."""
    day = {m.match_id: m.day for m in sims}
    plays = hs.occasions(sims, hs.RULES[0])
    seasons = len({m.season for m in sims}) or 1
    cells: dict[tuple[str, int], list[hs.Play]] = defaultdict(list)
    for p in plays:
        cells[(p.league, day[p.match_id].month)].append(p)
    rows = []
    for (league, month), ps in sorted(cells.items()):
        sm = hs.summarize_plays(ps)
        rows.append({"league": league, "month": month, "count": len(ps), "per_season": len(ps) / seasons, "clv": _est(sm.clv)})
    total = hs.summarize_plays(plays)
    return {"seasons": seasons, "plays": len(plays), "clv": _est(total.clv) if total else None, "rows": rows}


def twins_rows(sims: Sequence[hs.SimMatch]) -> list[list]:
    """Tabella compatta per le partite gemelle: campionato, probabilità d'apertura 1, X, 2, Over (o null), gol, giorno, id."""
    out = []
    for m in sims:
        p = m.fair_open.get("1X2")
        if not p:
            continue
        over = m.fair_open.get("OU2.5", {}).get("over")
        out.append([m.league, round(p["1"], 4), round(p["X"], 4), round(p["2"], 4), None if over is None else round(over, 4),
                    m.home_goals, m.away_goals, m.day.isoformat(), m.match_id])  # fmt: skip
    return out


# --- File dei risultati -------------------------------------------------------------------------------------


def learning_dir() -> Path:
    path = get_settings().data_cache_dir / "learning"
    path.mkdir(parents=True, exist_ok=True)
    return path


def refresh_learning(log=print) -> str:
    """Rifà tutte le prove e salva i risultati (lavoro settimanale)."""
    by_book, fixtures = sim_matches(STRATEGY_FIRST, LAST)
    sims = by_book["bet365"]
    log(f"partite storiche: {len(sims)}")
    report = {
        "computed_at": datetime.now(UTC).isoformat(),
        "strategies": strategy_report(sims, fixtures),
        "timing": timing_report(load_timing_books()),
        "calibration": calibration_report(sims),
        "value_map": value_map(sims),
    }
    folder = learning_dir()
    (folder / "learning.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    (folder / "twins.json").write_text(json.dumps(twins_rows(sims)), encoding="utf-8")
    load_learning.cache_clear()
    load_twins.cache_clear()
    passed = len(report["strategies"]["passed"])
    return f"strategie provate {report['strategies']['tested']}, passano {passed}; archivio quote {report['timing']['matches']} partite"


@lru_cache(maxsize=1)
def load_learning() -> dict | None:
    path = learning_dir() / "learning.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@lru_cache(maxsize=1)
def load_twins() -> list[list]:
    path = learning_dir() / "twins.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def passed_strategies() -> list[ss.Strategy]:
    """Le strategie trovate da Archie che hanno passato la conferma (D118): entrano nelle Occasioni."""
    report = load_learning()
    return [strategy_from(r["strategy"]) for r in (report or {}).get("strategies", {}).get("passed", [])]


# --- Partite gemelle ----------------------------------------------------------------------------------------

TWINS = 100


def twins(probs_1x2: dict[str, float], p_over: float | None, rows: Sequence[list] | None = None, k: int = TWINS) -> dict | None:
    """Le k partite passate con le probabilità d'apertura più vicine (1, 2 e, se c'è, Over) e come sono finite."""
    rows = load_twins() if rows is None else rows
    if not rows:
        return None
    use_over = p_over is not None

    def dist(r: list) -> float:
        d = (r[1] - probs_1x2["1"]) ** 2 + (r[3] - probs_1x2["2"]) ** 2
        if use_over:
            d += (r[4] - p_over) ** 2 if r[4] is not None else 1.0
        return d

    near = sorted(rows, key=dist)[:k]
    n = len(near)
    res = Counter("1" if r[5] > r[6] else "X" if r[5] == r[6] else "2" for r in near)
    with_over = [r for r in near if r[4] is not None]
    scores = Counter(f"{r[5]}-{r[6]}" for r in near).most_common(4)
    return {
        "n": n,
        "observed": {s: res[s] / n for s in ("1", "X", "2")},
        "expected": {s: sum(r[i] for r in near) / n for s, i in (("1", 1), ("X", 2), ("2", 3))},
        "over_observed": sum(r[5] + r[6] >= 3 for r in with_over) / len(with_over) if with_over else None,
        "over_expected": sum(r[4] for r in with_over) / len(with_over) if with_over else None,
        "avg_goals": sum(r[5] + r[6] for r in near) / n,
        "top_scores": [[s, c / n] for s, c in scores],
        "examples": [{"match_id": r[8], "league": r[0], "day": r[7], "score": f"{r[5]}-{r[6]}"} for r in near[:5]],
    }
