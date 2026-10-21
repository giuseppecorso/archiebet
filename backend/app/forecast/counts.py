"""Numeri di squadra (tiri, angoli, falli, cartellini): modello "fatti × subiti" e prova degli stili (D108).

Per ogni squadra e numero: media attesa = media del campionato (casa o trasferta) × forza "fatti" della squadra ×
forza "subiti" dell'avversario. Le forze sono medie della stagione fino al giorno prima, ristrette verso la media del
campionato con k partite fittizie. Distribuzione binomiale negativa (più dispersa della Poisson).
"""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

STATS = ("shots", "corners", "fouls", "cards")
LEAGUE_PRIOR_GAMES = 50  # la media del campionato a inizio stagione: quella della stagione prima, pesata come 50 partite


@dataclass(frozen=True)
class CountGame:
    match_id: int
    league: str
    season: str
    kickoff: datetime
    home: int
    away: int
    values: dict[str, tuple[int, int]]  # numero → (casa, ospite)


@dataclass(frozen=True)
class Ratios:
    """Forze prima della partita, come rapporto sulla media del campionato (1 = nella media)."""

    league_home: float
    league_away: float
    for_home: float
    against_home: float
    for_away: float
    against_away: float


@dataclass
class _Running:
    total: float = 0.0
    n: int = 0

    def add(self, x: float) -> None:
        self.total += x
        self.n += 1


@dataclass
class _Season:
    home: _Running = field(default_factory=_Running)
    away: _Running = field(default_factory=_Running)
    teams_for: dict[int, _Running] = field(default_factory=lambda: defaultdict(_Running))
    teams_against: dict[int, _Running] = field(default_factory=lambda: defaultdict(_Running))


def _mean(r: _Running, prior: float, prior_n: float) -> float:
    return (r.total + prior * prior_n) / (r.n + prior_n)


def pre_match_ratios(games: Sequence[CountGame], stat: str, k: float) -> dict[int, Ratios]:
    """Forze di ogni partita calcolate solo con le partite precedenti della stessa stagione (niente dati dal futuro).

    La prima stagione di ogni campionato serve solo da partenza: le sue partite non hanno forze.
    """
    out: dict[int, Ratios] = {}
    seasons: dict[tuple[str, str], _Season] = {}
    last_mean: dict[str, tuple[float, float]] = {}  # campionato → (casa, ospite) della stagione prima
    for g in sorted(games, key=lambda x: (x.kickoff, x.match_id)):
        key = (g.league, g.season)
        if key not in seasons:
            prev = [s for (lg, _), s in seasons.items() if lg == g.league]
            if prev:
                p = prev[-1]
                last_mean[g.league] = (p.home.total / max(p.home.n, 1), p.away.total / max(p.away.n, 1))
            seasons[key] = _Season()
        s = seasons[key]
        y_home, y_away = g.values[stat]
        if g.league in last_mean:
            ph, pa = last_mean[g.league]
            lh, la = _mean(s.home, ph, LEAGUE_PRIOR_GAMES), _mean(s.away, pa, LEAGUE_PRIOR_GAMES)
            avg = (lh + la) / 2
            out[g.match_id] = Ratios(
                lh, la,
                _mean(s.teams_for[g.home], avg, k) / avg, _mean(s.teams_against[g.home], avg, k) / avg,
                _mean(s.teams_for[g.away], avg, k) / avg, _mean(s.teams_against[g.away], avg, k) / avg,
            )  # fmt: skip
        s.home.add(y_home)
        s.away.add(y_away)
        s.teams_for[g.home].add(y_home)
        s.teams_against[g.home].add(y_away)
        s.teams_for[g.away].add(y_away)
        s.teams_against[g.away].add(y_home)
    return out


def expected(r: Ratios) -> tuple[float, float]:
    """Medie attese (casa, ospite) del modello base."""
    return r.league_home * r.for_home * r.against_away, r.league_away * r.for_away * r.against_home


def nb_logpmf(y: int, mean: float, size: float) -> float:
    """Log-probabilità binomiale negativa con media `mean` e dispersione `size` (varianza = mean + mean²/size)."""
    mean = max(mean, 1e-9)
    return (math.lgamma(y + size) - math.lgamma(size) - math.lgamma(y + 1)
            + size * math.log(size / (size + mean)) + y * math.log(mean / (size + mean)))  # fmt: skip


def nb_over(line: float, mean: float, size: float) -> float:
    """Probabilità di superare una linea .5 (es. Over 9.5 angoli)."""
    under = sum(math.exp(nb_logpmf(y, mean, size)) for y in range(int(math.floor(line)) + 1))
    return max(0.0, 1.0 - under)


@dataclass(frozen=True)
class Row:
    """Una partita pronta per la prova: numeri veri, medie del modello base, variabili di stile (casa, ospite)."""

    match_id: int
    season: str
    y: tuple[int, int]
    base: tuple[float, float]
    style: tuple[float, float]  # interazione per la squadra di casa e per l'ospite (0 = nessun incastro)


def log_lik_vec(y: np.ndarray, base: np.ndarray, style: np.ndarray, size: float, beta: float = 0.0) -> np.ndarray:
    """Log-verosimiglianza per partita (casa + ospite), vettoriale: y, base, style hanno forma (partite, 2)."""
    mean = np.maximum(base * np.exp(beta * style), 1e-9)
    ll = gammaln(y + size) - gammaln(size) - gammaln(y + 1) + size * np.log(size / (size + mean)) + y * np.log(mean / (size + mean))
    return ll.sum(axis=1)


def arrays(rows: Sequence[Row]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (np.array([r.y for r in rows], dtype=float), np.array([r.base for r in rows]), np.array([r.style for r in rows]))


def fit_size(rows: Sequence[Row]) -> float:
    y, base, style = arrays(rows)
    res = minimize_scalar(lambda ls: -log_lik_vec(y, base, style, math.exp(ls)).sum(), bounds=(math.log(0.5), math.log(1000)), method="bounded")
    return float(math.exp(res.x))


def fit_beta(rows: Sequence[Row], size: float) -> float:
    y, base, style = arrays(rows)
    res = minimize_scalar(lambda b: -log_lik_vec(y, base, style, size, b).sum(), bounds=(-2.0, 2.0), method="bounded")
    return float(res.x)


def gain(rows: Sequence[Row], size: float, beta: float) -> np.ndarray:
    """Per partita: log-verosimiglianza con lo stile meno quella del modello base (positivo = lo stile aiuta)."""
    y, base, style = arrays(rows)
    return log_lik_vec(y, base, style, size, beta) - log_lik_vec(y, base, style, size, 0.0)


def style_terms(driver: Ratios) -> tuple[float, float]:
    """Interazione di stile in logaritmo, per casa e ospite: forza "fatti" della squadra nel numero guida × forza "subiti"
    dell'avversario nello stesso numero (es. tiri fatti × tiri concessi; falli fatti × falli subiti)."""
    return (math.log(driver.for_home) * math.log(driver.against_away), math.log(driver.for_away) * math.log(driver.against_home))


def build_rows(games: Sequence[CountGame], target: str, driver: str, k: float) -> list[Row]:
    """Righe della prova: medie base sul numero target, stile dal numero driver (stesse partite, stessa k)."""
    t, d = pre_match_ratios(games, target, k), pre_match_ratios(games, driver, k)
    by_id = {g.match_id: g for g in games}
    rows = []
    for mid, r in t.items():
        if mid in d:
            g = by_id[mid]
            rows.append(Row(mid, g.season, g.values[target], expected(r), style_terms(d[mid])))
    return rows


def paired(diffs: np.ndarray) -> tuple[float, float]:
    """Media e errore standard delle differenze per partita."""
    return float(diffs.mean()), float(diffs.std(ddof=1) / math.sqrt(len(diffs)))


# --- Numeri attesi per la pagina partita (D109) ---------------------------------------------------------------------

# Parametri scelti dalla prova D108 in taratura: restringimento k e dispersione della binomiale negativa
MODEL_PARAMS = {"shots": (8, 24.6), "corners": (16, 12.1), "cards": (16, 1000.0)}
LINES = {"shots": (20.5, 22.5, 24.5, 26.5), "corners": (8.5, 9.5, 10.5, 11.5), "cards": (3.5, 4.5, 5.5)}
TEAM_LINES = {"shots": (9.5, 11.5, 13.5), "corners": (3.5, 4.5, 5.5), "cards": (1.5, 2.5)}


@dataclass(frozen=True)
class ExpectedCount:
    stat: str
    home: float
    away: float
    total_over: dict[float, float]  # linea → probabilità Over del totale
    home_over: dict[float, float]
    away_over: dict[float, float]


def total_size(means: Sequence[float], size: float) -> float:
    """Dispersione del totale di due binomiali negative indipendenti, per momenti: var = Σμ + Σμ²/size."""
    return sum(means) ** 2 / (sum(m * m for m in means) / size)


def expected_counts(games: Sequence[CountGame], target: CountGame) -> list[ExpectedCount]:
    """Numeri attesi di una partita da giocare: target va passata con valori qualsiasi, conta solo il passato."""
    out = []
    for stat, (k, size) in MODEL_PARAMS.items():
        ratios = pre_match_ratios([*games, target], stat, k).get(target.match_id)
        if ratios is None:
            continue
        mh, ma = expected(ratios)
        st = total_size((mh, ma), size)
        out.append(ExpectedCount(
            stat, mh, ma,
            {line: nb_over(line, mh + ma, st) for line in LINES[stat]},
            {line: nb_over(line, mh, size) for line in TEAM_LINES[stat]},
            {line: nb_over(line, ma, size) for line in TEAM_LINES[stat]},
        ))  # fmt: skip
    return out
