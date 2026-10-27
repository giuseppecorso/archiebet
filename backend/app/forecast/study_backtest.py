"""Prova dello studio sul passato (D140): walk-forward settimanale, varianti misurate con la log loss.

Legge solo la cache (schede delle partite da API-Football, D140, e calendari delle coppe, D89): niente rete.
"""

import math
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from app.forecast.dixon_coles import fit_dixon_coles, score_matrix, time_decay_weights
from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.study import MARKETS, first_half_share

COUNTRIES = {"Italia": (135, 136, 138, 942, 943), "Inghilterra": (39, 40), "Spagna": (140, 141), "Germania": (78, 79), "Francia": (61, 62)}
EUROPE = (2, 3, 848)
CUPS = (2, 3, 848, 137, 891, 45, 48, 143, 81, 66)
XI = 0.002
RIDGE = 8.0
WINDOW_DAYS = 3 * 365
REFIT_DAYS = 7
SAMPLE = 10
BASE_PRIOR = 24
SHORT_REST_DAYS = 3.5  # "al massimo 3 giorni prima" (con margine per gli orari)
EURO_AWAY_DAYS = 4.5
TUNING = (2023, 2024)
CONFIRMATION = (2025,)
# Mercati misurati: nome → esiti (le probabilità si rinormalizzano dentro il mercato)
EVAL_MARKETS = ("1X2", "OU2.5", "GG", "TGH0.5", "TGA0.5", "1T_OU0.5", "1T_TGH0.5", "1T_TGA0.5")


@dataclass(frozen=True)
class G:
    """Una partita finita."""

    id: int
    date: datetime
    league: int
    season: int
    home: int
    away: int
    hg: int
    ag: int
    hh: int  # gol di casa nel primo tempo
    ha: int
    xh: float | None
    xa: float | None
    starters: tuple[tuple[int, ...], tuple[int, ...]] = ((), ())
    contributions: tuple[dict, dict] = field(default=({}, {}))  # giocatore → gol + assist in questa partita


def outcome(market: str, sel: str, g: G) -> bool:
    return MARKETS[market].selections[sel](g.hg, g.ag, g.hh, g.ha)


# --- Probabilità veloci (gli stessi numeri di study.model_probabilities, solo per i mercati misurati) ---

_I, _J = np.meshgrid(np.arange(11), np.arange(11), indexing="ij")


def quick_probs(lam: float, mu: float, rho: float, share_home: float, share_away: float) -> dict[str, dict[str, float]]:
    m = score_matrix(lam, mu, rho, 10)
    m = m / m.sum()
    p1, px = float(m[_I > _J].sum()), float(m[_I == _J].sum())
    over = float(m[(_I + _J) > 2.5].sum())
    gg = float(m[(_I > 0) & (_J > 0)].sum())
    h0, a0 = float(m[0, :].sum()), float(m[:, 0].sum())
    l1, m1 = lam * share_home, mu * share_away
    return {
        "1X2": {"1": p1, "X": px, "2": 1 - p1 - px},
        "OU2.5": {"over": over, "under": 1 - over},
        "GG": {"yes": gg, "no": 1 - gg},
        "TGH0.5": {"over": 1 - h0, "under": h0},
        "TGA0.5": {"over": 1 - a0, "under": a0},
        "1T_OU0.5": {"over": 1 - math.exp(-(l1 + m1)), "under": math.exp(-(l1 + m1))},
        "1T_TGH0.5": {"over": 1 - math.exp(-l1), "under": math.exp(-l1)},
        "1T_TGA0.5": {"over": 1 - math.exp(-m1), "under": math.exp(-m1)},
    }


def with_field(probs: dict[str, dict[str, float]], hits: dict[tuple[str, str], tuple[int, int]], prior: float) -> dict[str, dict[str, float]]:
    """Media bayesiana con i fatti del campo (peso del modello = prior partite), rinormalizzata nel mercato."""
    if prior <= 0 and not hits:
        return probs
    out = {}
    for market, sels in probs.items():
        mixed = {}
        for sel, p in sels.items():
            k, n = hits.get((market, sel), (0, 0))
            mixed[sel] = (p * prior + k) / (prior + n) if prior + n > 0 else p
        total = sum(mixed.values())
        out[market] = {s: v / total for s, v in mixed.items()}
    return out


def match_loss(probs: dict[str, dict[str, float]], g: G) -> float:
    loss = 0.0
    for market in EVAL_MARKETS:
        sels = probs[market]
        won = next(s for s in sels if outcome(market, s, g))
        loss -= math.log(max(sels[won], 1e-9))
    return loss


# --- Ingredienti ---

def rest_flags(g: G, team: int, calendar: dict[int, list[tuple[datetime, bool]]]) -> tuple[bool, bool]:
    """(ha giocato al massimo 3 giorni prima, viene da una trasferta europea entro 4 giorni)."""
    dates = calendar.get(team, [])
    i = bisect_left(dates, (g.date, False)) - 1
    if i < 0:
        return False, False
    prev, euro_away = dates[i]
    gap = (g.date - prev).total_seconds() / 86400
    return gap <= SHORT_REST_DAYS, euro_away and gap <= EURO_AWAY_DAYS


def missing_share(team_games: Sequence[G], team: int, g: G) -> float:
    """Parte dei gol + assist della stagione (fin qui) di giocatori che oggi non sono titolari."""
    totals: dict[int, int] = defaultdict(int)
    for past in team_games:
        side = 0 if past.home == team else 1
        for pid, ga in past.contributions[side].items():
            totals[pid] += ga
    all_ga = sum(totals.values())
    if all_ga < 5:
        return 0.0
    starters = set(g.starters[0 if g.home == team else 1])
    if not starters:
        return 0.0
    return sum(v for pid, v in totals.items() if pid not in starters) / all_ga


def field_hits(home_games: Sequence[G], away_games: Sequence[G]) -> dict[tuple[str, str], tuple[int, int]]:
    out = {}
    for market in EVAL_MARKETS:
        for sel in MARKETS[market].selections:
            k = sum(outcome(market, sel, x) for x in home_games) + sum(outcome(market, sel, x) for x in away_games)
            out[(market, sel)] = (k, len(home_games) + len(away_games))
    return out


# --- Il walk-forward ---

@dataclass
class Prepared:
    """Tutto ciò che serve per una partita da prevedere, calcolato una volta: poi le varianti costano poco."""

    g: G
    goals_country: tuple[float, float, float]  # λ, μ, ρ dal modello per paese
    goals_league: tuple[float, float, float]
    xg_league: tuple[float, float] | None
    shares: tuple[float, float]
    hits: dict
    short: tuple[bool, bool]
    euro: tuple[bool, bool]
    missing: tuple[float, float]


def _fit(games: Sequence[G], when: datetime, use_xg: bool = False):
    train = [x for x in games if when - timedelta(days=WINDOW_DAYS) <= x.date < when and (not use_xg or (x.xh is not None and x.xa is not None))]
    if len(train) < 50:
        return None
    hg = [x.xh if use_xg else x.hg for x in train]
    ag = [x.xa if use_xg else x.ag for x in train]
    return fit_dixon_coles([x.home for x in train], [x.away for x in train], hg, ag,
                           weights=time_decay_weights([x.date for x in train], when, XI), ridge=RIDGE)  # fmt: skip


def _shares(prior: Sequence[G], g: G) -> tuple[float, float]:
    goals = sum(x.hg + x.ag for x in prior)
    league = sum(x.hh + x.ha for x in prior) / goals if goals else 0.45
    s, s1, c, c1 = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    for x in prior:
        for team, a, a1, b, b1 in ((x.home, x.hg, x.hh, x.ag, x.ha), (x.away, x.ag, x.ha, x.hg, x.hh)):
            s[team] += a
            s1[team] += a1
            c[team] += b
            c1[team] += b1

    def mix(att, dfn):
        return (first_half_share(s1[att], s[att], league) + first_half_share(c1[dfn], c[dfn], league)) / 2

    return mix(g.home, g.away), mix(g.away, g.home)


def _venue(prior: Sequence[G], team: int, home: bool, season: int) -> list[G]:
    mine = [x for x in reversed(prior) if (x.home if home else x.away) == team]
    this = [x for x in mine if x.season == season][:SAMPLE]
    return this if len(this) >= 6 else (this + [x for x in mine if x.season != season])[:SAMPLE]


def prepare(games: Sequence[G], calendar: dict, seasons: Iterable[int], log: Callable[[str], None] = print) -> list[Prepared]:
    """Per ogni partita delle stagioni da valutare, i modelli stimati con le sole partite precedenti (ristima settimanale)."""
    seasons = set(seasons)
    by_country = {c: sorted((x for x in games if x.league in leagues), key=lambda x: x.date) for c, leagues in COUNTRIES.items()}
    out = []
    for country, cgames in by_country.items():
        targets = [x for x in cgames if x.season in seasons]
        if not targets:
            continue
        week_start = targets[0].date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = targets[-1].date
        while week_start <= end:
            week_end = week_start + timedelta(days=REFIT_DAYS)
            todo = [x for x in targets if week_start <= x.date < week_end]
            if todo:
                fit_c = _fit(cgames, week_start)
                fits_l, fits_x, before = {}, {}, {}
                for league in {x.league for x in todo}:
                    lg = [x for x in cgames if x.league == league]
                    fits_l[league], fits_x[league] = _fit(lg, week_start), _fit(lg, week_start, use_xg=True)
                    before[league] = [x for x in lg if x.date < week_start]  # una volta per settimana e campionato
                for g in todo:
                    fl, fx = fits_l[g.league], fits_x[g.league]
                    if fit_c is None or fl is None or not all(f.has_team(t) for f in (fit_c, fl) for t in (g.home, g.away)):
                        continue
                    prior = [x for x in before[g.league] if x.season >= g.season - 1]
                    hv, av = _venue(prior, g.home, True, g.season), _venue(prior, g.away, False, g.season)
                    if len(hv) < 4 or len(av) < 4:
                        continue
                    team_season = lambda t: [x for x in prior if x.season == g.season and t in (x.home, x.away)]  # noqa: E731
                    xg = fx.expected_goals(g.home, g.away) if fx is not None and fx.has_team(g.home) and fx.has_team(g.away) else None
                    flags = (rest_flags(g, g.home, calendar), rest_flags(g, g.away, calendar))
                    out.append(Prepared(
                        g, (*fit_c.expected_goals(g.home, g.away), fit_c.rho), (*fl.expected_goals(g.home, g.away), fl.rho), xg,
                        _shares(prior, g), field_hits(hv, av), (flags[0][0], flags[1][0]), (flags[0][1], flags[1][1]),
                        (missing_share(team_season(g.home), g.home, g), missing_share(team_season(g.away), g.away, g)),
                    ))  # fmt: skip
            week_start = week_end
        log(f"{country}: {sum(1 for p in out if p.g.league in COUNTRIES[country])} partite pronte")
    return out


@dataclass(frozen=True)
class Config:
    per_league: bool = False
    xg_weight: float = 0.0
    beta_short: float = 0.0
    beta_euro: float = 0.0
    gamma: float = 0.0
    prior: float = BASE_PRIOR


def loss(p: Prepared, c: Config) -> float:
    lam, mu, rho = p.goals_league if c.per_league else p.goals_country
    if c.xg_weight and p.xg_league is not None:
        lam = (1 - c.xg_weight) * lam + c.xg_weight * p.xg_league[0]
        mu = (1 - c.xg_weight) * mu + c.xg_weight * p.xg_league[1]
    lam *= math.exp(c.beta_short * p.short[0] + c.beta_euro * p.euro[0] + c.gamma * p.missing[0])
    mu *= math.exp(c.beta_short * p.short[1] + c.beta_euro * p.euro[1] + c.gamma * p.missing[1])
    return match_loss(with_field(quick_probs(lam, mu, rho, *p.shares), p.hits, c.prior), p.g)


@dataclass
class VariantResult:
    name: str
    config: Config
    tuning: Estimate
    confirmation: Estimate

    @property
    def passed(self) -> bool:
        return self.tuning.mean > 2 * self.tuning.std_error and self.confirmation.mean > 2 * self.confirmation.std_error


def improvement(prepared: Sequence[Prepared], base: Config, variant: Config, seasons: Iterable[int]) -> Estimate:
    """Quanto la variante abbassa la log loss rispetto alla base, partita per partita (positivo = meglio)."""
    seasons = set(seasons)
    rows = [p for p in prepared if p.g.season in seasons]
    diffs = [loss(p, base) - loss(p, variant) for p in rows]
    return clustered_mean(diffs, [p.g.id for p in rows])


def best_on_tuning(prepared: Sequence[Prepared], base: Config, candidates: Sequence[Config]) -> Config:
    tuning = [p for p in prepared if p.g.season in TUNING]
    return min(candidates, key=lambda c: sum(loss(p, c) for p in tuning))


def run_variants(prepared: Sequence[Prepared], log: Callable[[str], None] = print) -> list[VariantResult]:
    base = Config()
    grids = {
        "V1 un modello per campionato": [Config(per_league=True)],
        "V2 xG": [Config(xg_weight=w) for w in (0.25, 0.5, 0.75)],
        "V3 stanchezza": [Config(beta_short=b, beta_euro=e) for b in (-0.15, -0.10, -0.05, 0.0, 0.05) for e in (-0.15, -0.10, -0.05, 0.0, 0.05)],
        "V4 assenti": [Config(gamma=g) for g in (-0.6, -0.5, -0.4, -0.3, -0.2, -0.1, 0.0)],
        "V5 peso dei fatti del campo": [Config(prior=w) for w in (0, 12, 48)],
    }
    out = []
    for name, candidates in grids.items():
        chosen = best_on_tuning(prepared, base, candidates)
        result = VariantResult(name, chosen, improvement(prepared, base, chosen, TUNING), improvement(prepared, base, chosen, CONFIRMATION))
        log(f"{name}: scelto {chosen} | taratura {result.tuning.mean:+.4f} ± {result.tuning.std_error:.4f} "
            f"| conferma {result.confirmation.mean:+.4f} ± {result.confirmation.std_error:.4f} | {'PASSA' if result.passed else 'non passa'}")  # fmt: skip
        out.append(result)
    return out


def combined(prepared: Sequence[Prepared], results: Sequence[VariantResult]) -> Config:
    """La configurazione con tutte le varianti che passano."""
    c = Config()
    for r in results:
        if r.passed:
            c = Config(per_league=c.per_league or r.config.per_league, xg_weight=r.config.xg_weight or c.xg_weight,
                       beta_short=r.config.beta_short or c.beta_short, beta_euro=r.config.beta_euro or c.beta_euro,
                       gamma=r.config.gamma or c.gamma, prior=r.config.prior if r.config.prior != BASE_PRIOR else c.prior)  # fmt: skip
    return c


# --- Caricamento dalla cache ---

def load(cache, fixtures_for: Callable[[int, int], list]) -> tuple[list[G], dict[int, list[tuple[datetime, bool]]]]:
    """Partite dei 13 campionati (dalle schede in cache) e calendario di ogni squadra con le coppe."""
    from app.ingest.af_detail import FOREVER, detail_key
    from app.adapters.cache import MISSING

    games = []
    calendar: dict[int, list[tuple[datetime, bool]]] = defaultdict(list)
    for leagues in COUNTRIES.values():
        for league in leagues:
            for season in (2022, 2023, 2024, 2025):
                for f in fixtures_for(league, season):
                    d = cache.get(detail_key(f.id), FOREVER)
                    if d is MISSING or d["status"] not in ("FT", "AET", "PEN") or None in d["goals"] or None in d["ht"]:
                        continue
                    date = datetime.fromisoformat(d["date"])
                    contrib = tuple({row[0]: row[4] + row[5] for row in d["players"].get(side, []) if row[4] + row[5]} for side in ("home", "away"))
                    stats = d.get("stats") or {}
                    games.append(G(d["id"], date, league, season, d["home"], d["away"], d["goals"][0], d["goals"][1], d["ht"][0], d["ht"][1],
                                   (stats.get("home") or {}).get("xg"), (stats.get("away") or {}).get("xg"),
                                   (tuple(d["starters"].get("home", [])), tuple(d["starters"].get("away", []))), contrib))  # fmt: skip
                    calendar[d["home"]].append((date, False))
                    calendar[d["away"]].append((date, False))
    for cup in CUPS:
        for season in (2022, 2023, 2024, 2025):
            for f in fixtures_for(cup, season):
                if f.status != "finished" and f.status_short not in ("FT", "AET", "PEN"):
                    continue
                calendar[f.home.id].append((f.kickoff_at, False))
                calendar[f.away.id].append((f.kickoff_at, cup in EUROPE))
    for team in calendar:
        calendar[team] = sorted(set(calendar[team]))
    return sorted(games, key=lambda x: x.date), calendar
