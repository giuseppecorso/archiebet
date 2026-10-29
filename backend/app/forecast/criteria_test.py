"""Prova D156: ogni criterio col suo peso, stimato sul passato sopra lo studio attuale (D142).

Criteri: (C1) peso dei giocatori in attacco, (C2) qualità complessiva dei titolari, (C3) motivazione di classifica,
(C4) meteo. Walk-forward settimanale di D140 (study_backtest.prepare), stessi 8 mercati e stessa log loss.
Pesi per minima log loss sulle stagioni di taratura; miglioramento in taratura fuori campione (stimati su una stagione,
misurati sull'altra), conferma sulla stagione successiva con i pesi di tutta la taratura. Legge solo la cache.
"""

import math
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from scipy.optimize import minimize

from app.forecast import study_backtest as bt
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.player_weight import WINDOW_DAYS, Appearance, LineupChange, PlayerBook, RoleMeans, lineup_change, role_means
from app.forecast.study import BAD_WEATHER, TableSpot, goal_of

LEAGUES = (135, 136, 39, 140, 78, 61)  # campionati con le statistiche dei giocatori
PLAYER_SEASONS = (2021, 2022, 2023, 2024, 2025)  # 2021/22 solo come storico dei giocatori
BASE = bt.Config(per_league=True, xg_weight=0.75, prior=192.0)  # lo studio di oggi (D142)
MOTIVATED = ("vertice", "salvezza")


@dataclass(frozen=True)
class Weights:
    a: float = 0.0  # C1 attacco dei titolari
    b: float = 0.0  # C2 qualità propria sui gol fatti
    c: float = 0.0  # C2 qualità avversaria sui gol subiti
    m: float = 0.0  # C3 motivazione
    w: float = 0.0  # C4 meteo
    alpha: float = 1.0  # D160 ricalibrazione: p' ∝ p^alpha in ogni mercato
    market: float = 0.0  # D163 peso del mercato: λ = λ_studio^(1−w) · λ_mercato^w


@dataclass
class Row:
    p: bt.Prepared
    lam: float  # gol attesi della base (modello per campionato, 75% xG)
    mu: float
    rho: float
    lineup: tuple[LineupChange | None, LineupChange | None]
    motivated: tuple[int, int]  # 1 se la squadra lotta per qualcosa e l'avversaria non ha più obiettivi
    bad_weather: int | None  # 1 pioggia o vento forti, 0 no, None meteo sconosciuto
    market: tuple[float, float] | None = None  # gol attesi del mercato (Pinnacle pre-partita), D163


def factors(r: Row, x: Weights) -> tuple[float, float]:
    lh, la = r.lineup
    ah, rh = (lh.attack, lh.quality) if lh else (0.0, 0.0)
    aa, ra = (la.attack, la.quality) if la else (0.0, 0.0)
    bad = r.bad_weather or 0
    home = x.a * ah + x.b * rh - x.c * ra + x.m * r.motivated[0] + x.w * bad
    away = x.a * aa + x.b * ra - x.c * rh + x.m * r.motivated[1] + x.w * bad
    return math.exp(home), math.exp(away)


def row_loss(r: Row, x: Weights) -> float:
    return bt.match_loss(probabilities(r, x), r.p.g)


def blended(r: Row, x: Weights) -> tuple[float, float]:
    """Gol attesi dello studio uniti a quelli del mercato (media geometrica con peso x.market), poi gli altri criteri."""
    lam, mu = r.lam, r.mu
    w = min(max(x.market, 0.0), 1.0)  # D163: il peso sta tra 0 (solo studio) e 1 (solo mercato), come pre-registrato
    if w and r.market is not None:
        lam = lam ** (1 - w) * r.market[0] ** w
        mu = mu ** (1 - w) * r.market[1] ** w
    fh, fa = factors(r, x)
    return lam * fh, mu * fa


def probabilities(r: Row, x: Weights) -> dict[str, dict[str, float]]:
    lam, mu = blended(r, x)
    return recalibrate(bt.with_field(bt.quick_probs(lam, mu, r.rho, *r.p.shares), r.p.hits, BASE.prior), x.alpha)


def recalibrate(probs: dict[str, dict[str, float]], alpha: float) -> dict[str, dict[str, float]]:
    """Calibrazione a potenza (D160): alpha > 1 allontana le probabilità da 50%, alpha < 1 le avvicina."""
    if alpha == 1.0:
        return probs
    out = {}
    for market, sels in probs.items():
        powered = {k: max(v, 1e-12) ** alpha for k, v in sels.items()}
        total = sum(powered.values())
        out[market] = {k: v / total for k, v in powered.items()}
    return out


# --- Ingredienti per partita ---

def base_goals(p: bt.Prepared) -> tuple[float, float, float]:
    lam, mu, rho = p.goals_league
    if p.xg_league is not None:
        lam = (1 - BASE.xg_weight) * lam + BASE.xg_weight * p.xg_league[0]
        mu = (1 - BASE.xg_weight) * mu + BASE.xg_weight * p.xg_league[1]
    return lam, mu, rho


def motivation_flags(games: Sequence[bt.G]) -> dict[int, tuple[int, int]]:
    """Per ogni partita, la classifica della stagione prima del calcio d'inizio (regola D138)."""
    out = {}
    by_season: dict[tuple[int, int], list[bt.G]] = defaultdict(list)
    for g in games:
        by_season[(g.league, g.season)].append(g)
    for season_games in by_season.values():
        season_games.sort(key=lambda g: g.date)
        pts, played, diff = defaultdict(int), defaultdict(int), defaultdict(int)
        for g in season_games:
            order = sorted(played, key=lambda t: (pts[t], diff[t]), reverse=True)
            n = len(order)
            flags = (0, 0)
            if n >= 6 and g.home in played and g.away in played:
                top, safe = pts[order[1]], pts[order[n - 4]]
                spot = {t: TableSpot(i + 1, n, pts[t], played[t], top, safe) for i, t in enumerate(order)}
                gh, ga = goal_of(spot[g.home]), goal_of(spot[g.away])
                flags = (int(gh in MOTIVATED and ga == "nessun obiettivo"), int(ga in MOTIVATED and gh == "nessun obiettivo"))
            out[g.id] = flags
            for team, mine, theirs in ((g.home, g.hg, g.ag), (g.away, g.ag, g.hg)):
                played[team] += 1
                diff[team] += mine - theirs
                pts[team] += 3 if mine > theirs else 1 if mine == theirs else 0
    return out


class _Means:
    """Medie del ruolo per campionato con le presenze dei 365 giorni prima (una volta per settimana)."""

    def __init__(self, apps_by_league: Mapping[int, Sequence[Appearance]]):
        self.apps = {lg: sorted(a, key=lambda x: x.date) for lg, a in apps_by_league.items()}
        self.dates = {lg: [x.date for x in a] for lg, a in self.apps.items()}
        self.memo: dict[tuple[int, int, int], RoleMeans] = {}

    def at(self, league: int, when: datetime) -> RoleMeans:
        year, week, _ = when.isocalendar()
        key = (league, year, week)
        if key not in self.memo:
            start = when - timedelta(days=when.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            d = self.dates[league]
            self.memo[key] = role_means(self.apps[league][bisect_left(d, start - timedelta(days=WINDOW_DAYS)) : bisect_left(d, start)])
        return self.memo[key]


def build_rows(prepared: Sequence[bt.Prepared], games: Sequence[bt.G], apps_by_league: Mapping[int, Sequence[Appearance]],
               weather: Mapping[tuple[str, int, int], tuple[float, float]],
               market: Mapping[tuple[str, int, int], tuple[float, float]] | None = None) -> list[Row]:  # fmt: skip
    book = PlayerBook(a for apps in apps_by_league.values() for a in apps)
    means = _Means(apps_by_league)
    motivation = motivation_flags(games)
    rows = []
    for p in prepared:
        g = p.g
        if g.league not in LEAGUES:
            continue
        m = means.at(g.league, g.date)
        lineup = []
        for team in (g.home, g.away):
            starters = book.starters(team, g.id)
            lineup.append(lineup_change(book, team, [(a.player, a.position) for a in starters], g.date, m) if len(starters) == 11 else None)
        w = next((weather[k] for d in (0, -1, 1) if (k := ((g.date + timedelta(days=d)).date().isoformat(), g.home, g.away)) in weather), None)
        bad = None if w is None else int(w[0] >= BAD_WEATHER[0] or w[1] >= BAD_WEATHER[1])
        mk = next((market[k] for d in (0, -1, 1) if (k := ((g.date + timedelta(days=d)).date().isoformat(), g.home, g.away)) in market), None) if market else None
        rows.append(Row(p, *base_goals(p), tuple(lineup), motivation.get(g.id, (0, 0)), bad, mk))
    return rows


# --- Stima e misura ---

CRITERIA: dict[str, tuple[str, ...]] = {
    "C1 peso dei giocatori in attacco": ("a",),
    "C2 qualità dei titolari": ("b", "c"),
    "C3 motivazione": ("m",),
    "C4 meteo": ("w",),
    "C5 ricalibrazione (D160)": ("alpha",),
    "C6 unione con il mercato (D163)": ("market",),
}


def _relevant(r: Row, free: Sequence[str]) -> bool:
    """Le partite in cui i parametri liberi cambiano qualcosa (le altre hanno perdita costante: non servono alla stima)."""
    if {"a", "b", "c"} & set(free) and any(r.lineup):
        return True
    if "m" in free and any(r.motivated):
        return True
    if "alpha" in free:
        return True
    if "market" in free:
        return r.market is not None
    return "w" in free and bool(r.bad_weather)


def fit(rows: Sequence[Row], free: Sequence[str], start: Weights = Weights()) -> Weights:
    """Pesi liberi per minima log loss totale (gli altri restano quelli di `start`)."""
    used = [r for r in rows if _relevant(r, free)]
    if not used:
        return start

    def objective(v):
        x = replace(start, **dict(zip(free, v)))
        return sum(row_loss(r, x) for r in used)

    res = minimize(objective, [getattr(start, f) for f in free], method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 400})
    return replace(start, **dict(zip(free, res.x)))


def improvement(rows: Sequence[Row], x: Weights, base: Weights = Weights()) -> list[float]:
    return [row_loss(r, base) - row_loss(r, x) for r in rows]


@dataclass(frozen=True)
class CriterionResult:
    name: str
    weights: Weights
    tuning: Estimate
    confirmation: Estimate

    @property
    def passed(self) -> bool:
        return self.tuning.mean > 2 * self.tuning.std_error and self.confirmation.mean > 2 * self.confirmation.std_error


def evaluate(rows: Sequence[Row], name: str, free: Sequence[str], only: Callable[[Row], bool] = lambda r: True,
             log: Callable[[str], None] = print) -> CriterionResult:  # fmt: skip
    """Taratura fuori campione (stima su una stagione, misura sull'altra), poi conferma con la stima di tutta la taratura."""
    rows = [r for r in rows if only(r)]
    first, second = ([r for r in rows if r.p.g.season == s] for s in bt.TUNING)
    diffs, ids = [], []
    for train, test in ((first, second), (second, first)):
        x = fit(train, free)
        diffs += improvement(test, x)
        ids += [r.p.g.id for r in test]
    tuning = clustered_mean(diffs, ids)
    x = fit(first + second, free)
    confirm = [r for r in rows if r.p.g.season in bt.CONFIRMATION]
    result = CriterionResult(name, x, tuning, clustered_mean(improvement(confirm, x), [r.p.g.id for r in confirm]))
    log(f"{name}: pesi {x} | taratura {tuning.mean:+.4f} ± {tuning.std_error:.4f} | conferma {result.confirmation.mean:+.4f} "
        f"± {result.confirmation.std_error:.4f} | {'PASSA' if result.passed else 'non passa'}")  # fmt: skip
    return result


def run(rows: Sequence[Row], log: Callable[[str], None] = print) -> tuple[list[CriterionResult], CriterionResult | None]:
    results = []
    for name, free in CRITERIA.items():
        only = (lambda r: r.bad_weather is not None) if free == ("w",) else (lambda r: r.market is not None) if free == ("market",) else (lambda r: True)
        results.append(evaluate(rows, name, free, only, log))
    passing = [f for r, (_, free) in zip(results, CRITERIA.items()) if r.passed for f in free]
    together = evaluate(rows, "Insieme quelli che passano", passing, log=log) if len(passing) > 1 else None
    return results, together


# --- Caricamento dalla cache ---

def load_appearances(cache, fixtures_for: Callable[[int, int], list]) -> dict[int, list[Appearance]]:
    from app.adapters.cache import MISSING
    from app.forecast.player_weight import parse_appearances
    from app.ingest.af_stats import FOREVER

    out: dict[int, list[Appearance]] = defaultdict(list)
    for league in LEAGUES:
        for season in PLAYER_SEASONS:
            for f in fixtures_for(league, season):
                if f.status != "finished":
                    continue
                body = cache.get(f"fixtures/players?fixture={f.id}", FOREVER)
                if body is not MISSING:
                    out[league] += parse_appearances(body, f.id, f.kickoff_at)
    return out


def load_weather(db) -> dict[tuple[str, int, int], tuple[float, float]]:
    """Pioggia e vento di D76 (archivio Open-Meteo, salvato per le partite di football-data), indicizzati per
    (giorno, squadra di casa, squadra ospite) con gli id di API-Football: le stesse partite stanno in righe diverse."""
    import json

    from sqlalchemy import select

    from app.config import get_settings
    from app.models import Match, TeamAlias

    path = get_settings().data_cache_dir / "weather" / "raw.json"
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    af = {a.team_id: int(a.alias) for a in db.scalars(select(TeamAlias).where(TeamAlias.source == "api-football")) if a.alias.isdigit()}
    out: dict[tuple[str, int, int], tuple[float, float]] = {}
    ids = [int(k) for k in raw]
    for i in range(0, len(ids), 900):
        for m in db.scalars(select(Match).where(Match.id.in_(ids[i : i + 900]))):
            h, a = af.get(m.home_team_id), af.get(m.away_team_id)
            if h is not None and a is not None:
                w = raw[str(m.id)]
                out[(m.kickoff_at.date().isoformat(), h, a)] = (w[0], w[1])
    return out


def load_market(db) -> dict[tuple[str, int, int], tuple[float, float]]:
    """Gol attesi del mercato (D163) dalle quote Pinnacle pre-partita di football-data: 1X2 senza margine (Shin) e
    Under/Over 2.5 (proporzionale), indicizzati come il meteo per (giorno, casa, ospite) con gli id di API-Football."""
    from collections import defaultdict as dd

    from sqlalchemy import select

    from app.forecast.demargin import proportional, shin
    from app.forecast.live import fit_rates
    from app.models import Match, MatchOdds, TeamAlias

    af = {a.team_id: int(a.alias) for a in db.scalars(select(TeamAlias).where(TeamAlias.source == "api-football")) if a.alias.isdigit()}
    prices: dict[int, dict[str, dict[str, float]]] = dd(lambda: dd(dict))
    for o in db.scalars(select(MatchOdds).where(MatchOdds.source == "football-data", MatchOdds.bookmaker == "pinnacle", MatchOdds.is_closing.is_(False),
                                                 MatchOdds.market.in_(("1X2", "OU2.5")))):  # fmt: skip
        prices[o.match_id][o.market][o.selection] = float(o.price)
    out: dict[tuple[str, int, int], tuple[float, float]] = {}
    ids = [mid for mid, mk in prices.items() if len(mk.get("1X2", {})) == 3]
    for i in range(0, len(ids), 900):
        for m in db.scalars(select(Match).where(Match.id.in_(ids[i : i + 900]), Match.season >= "2022/23")):
            h, a = af.get(m.home_team_id), af.get(m.away_team_id)
            if h is None or a is None:
                continue
            x = prices[m.id]["1X2"]
            p1, _, p2 = shin([x["1"], x["X"], x["2"]])
            ou = prices[m.id].get("OU2.5", {})
            p_over = proportional([ou["over"], ou["under"]])[0] if len(ou) == 2 else None
            out[(m.kickoff_at.date().isoformat(), h, a)] = fit_rates(p1, p2, p_over)
    return out


# --- D156-bis: taratura per fascia di quota giusta ---

BANDS = (("bassa (fino a 1,67)", 0.6, 1.01), ("media (1,67-2,50)", 0.4, 0.6), ("alta (oltre 2,50)", 0.0, 0.4))


@dataclass(frozen=True)
class Band:
    name: str
    n: int
    predicted: float  # probabilità media prevista
    observed: float  # frequenza con cui è successo
    gap: Estimate  # osservata − prevista, errore standard per partita

    @property
    def calibrated(self) -> bool:
        return abs(self.gap.mean) <= 2 * self.gap.std_error


def bands(rows: Sequence[Row], x: Weights = Weights()) -> list[Band]:
    """Ogni esito degli 8 mercati, per fascia di quota giusta: previsto contro successo."""
    items: dict[str, list[tuple[float, int, int]]] = defaultdict(list)
    for r in rows:
        probs = probabilities(r, x)
        for market in bt.EVAL_MARKETS:
            for sel, p in probs[market].items():
                name = next(n for n, lo, hi in BANDS if lo <= p < hi)
                items[name].append((p, int(bt.outcome(market, sel, r.p.g)), r.p.g.id))
    out = []
    for name, _, _ in BANDS:
        rows_b = items.get(name, [])
        if not rows_b:
            continue
        gap = clustered_mean([o - p for p, o, _ in rows_b], [i for _, _, i in rows_b])
        out.append(Band(name, len(rows_b), sum(p for p, _, _ in rows_b) / len(rows_b), sum(o for _, o, _ in rows_b) / len(rows_b), gap))
    return out


def log_bands(title: str, found: Sequence[Band], log: Callable[[str], None] = print) -> None:
    log(title)
    for b in found:
        log(f"  quota {b.name}: {b.n} esiti, previsto {b.predicted:.1%}, successo {b.observed:.1%}, "
            f"differenza {b.gap.mean:+.1%} ± {b.gap.std_error:.1%} -> {'ben tarato' if b.calibrated else 'NON tarato'}")  # fmt: skip
