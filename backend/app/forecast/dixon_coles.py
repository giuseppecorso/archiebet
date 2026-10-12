"""Modello Dixon-Coles (1997): probabilità di ogni risultato esatto.

Idea in breve:
- i gol di casa seguono una Poisson di media  λ = exp(campo + attacco_casa − difesa_ospite)
- i gol fuori seguono una Poisson di media    μ = exp(attacco_ospite − difesa_casa)
- la correzione τ (rho) aggiusta i risultati bassi (0-0, 1-0, 0-1, 1-1), che la Poisson pura sbaglia
- ogni partita pesa di più se è recente (pesi esponenziali nel tempo, vedi `time_decay_weights`)

Convenzione: difesa ALTA = difesa forte (subisce meno). Attacchi e difese sono centrati
(la somma degli attacchi è 0), quindi una squadra "media" ha attacco 0 e difesa 0.
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

RHO_BOUNDS = (-0.3, 0.3)
MAX_GOALS = 10  # la matrice dei risultati va da 0 a 10 gol per squadra
_TAU_FLOOR = 1e-10  # τ non può essere ≤ 0 (logaritmo): con valori estremi lo teniamo appena sopra zero


def tau(home_goals: np.ndarray, away_goals: np.ndarray, lam: np.ndarray, mu: np.ndarray, rho: float) -> np.ndarray:
    """Correzione di Dixon-Coles per i risultati bassi; vale 1 per tutti gli altri."""
    hg, ag = np.asarray(home_goals), np.asarray(away_goals)
    lam, mu = np.broadcast_to(lam, hg.shape), np.broadcast_to(mu, hg.shape)
    t = np.ones(hg.shape, dtype=float)
    t = np.where((hg == 0) & (ag == 0), 1 - lam * mu * rho, t)
    t = np.where((hg == 0) & (ag == 1), 1 + lam * rho, t)
    t = np.where((hg == 1) & (ag == 0), 1 + mu * rho, t)
    t = np.where((hg == 1) & (ag == 1), 1 - rho, t)
    return t


def score_matrix(lam: float, mu: float, rho: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    """Matrice P[i, j] = probabilità che finisca i (casa) - j (fuori). Somma 1."""
    goals = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu))
    low = np.array([[0, 0], [0, 1], [1, 0], [1, 1]])
    m[low[:, 0], low[:, 1]] *= np.maximum(tau(low[:, 0], low[:, 1], lam, mu, rho), 0.0)
    return m / m.sum()  # la coda oltre max_goals è trascurabile: rinormalizziamo


def time_decay_weights(dates: Sequence[datetime], reference: datetime, xi_per_day: float) -> np.ndarray:
    """Peso exp(−ξ·giorni) di ogni partita rispetto alla data di riferimento.

    Una partita successiva al riferimento è un errore (dati dal futuro, principio 3).
    """
    days = np.array([(reference - d).total_seconds() / 86400 for d in dates], dtype=float)
    if (days < 0).any():
        raise ValueError("Partita successiva alla data di riferimento: dati dal futuro")
    return np.exp(-xi_per_day * days)


@dataclass(frozen=True)
class DixonColesFit:
    teams: tuple[Hashable, ...]
    attack: np.ndarray
    defence: np.ndarray
    home_advantage: float
    rho: float
    n_matches: int
    converged: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", {t: i for i, t in enumerate(self.teams)})

    def has_team(self, team: Hashable) -> bool:
        return team in self._index

    def expected_goals(self, home: Hashable, away: Hashable) -> tuple[float, float]:
        h, a = self._index[home], self._index[away]
        lam = np.exp(self.home_advantage + self.attack[h] - self.defence[a])
        mu = np.exp(self.attack[a] - self.defence[h])
        return float(lam), float(mu)

    def score_matrix(self, home: Hashable, away: Hashable, max_goals: int = MAX_GOALS) -> np.ndarray:
        lam, mu = self.expected_goals(home, away)
        return score_matrix(lam, mu, self.rho, max_goals)


def _objective(params, n, hi, ai, hg, ag, w, ridge):
    """Log-verosimiglianza negativa (media pesata) + penalità, con il suo gradiente esatto."""
    att, dfc = params[:n], params[n : 2 * n]
    gamma, rho = params[2 * n], params[2 * n + 1]
    log_lam = gamma + att[hi] - dfc[ai]
    log_mu = att[ai] - dfc[hi]
    lam, mu = np.exp(log_lam), np.exp(log_mu)

    t = np.maximum(tau(hg, ag, lam, mu, rho), _TAU_FLOOR)
    ll = np.log(t) + hg * log_lam - lam + ag * log_mu - mu  # i termini log(x!) sono costanti

    # Derivate di log τ rispetto a log λ, log μ e rho (diverse da 0 solo sui risultati bassi)
    d00, d01, d10, d11 = (hg == 0) & (ag == 0), (hg == 0) & (ag == 1), (hg == 1) & (ag == 0), (hg == 1) & (ag == 1)
    dt_lam = np.where(d00, -lam * mu * rho, 0.0) + np.where(d01, lam * rho, 0.0)
    dt_mu = np.where(d00, -lam * mu * rho, 0.0) + np.where(d10, mu * rho, 0.0)
    dt_rho = (
        np.where(d00, -lam * mu, 0.0) + np.where(d01, lam, 0.0) + np.where(d10, mu, 0.0) + np.where(d11, -1.0, 0.0)
    ) / t
    g_lam = w * (hg - lam + dt_lam / t)  # derivata rispetto a log λ, partita per partita
    g_mu = w * (ag - mu + dt_mu / t)

    total_w = w.sum()
    value = -(w * ll).sum() / total_w
    grad = np.empty_like(params)
    grad[:n] = -(np.bincount(hi, g_lam, n) + np.bincount(ai, g_mu, n)) / total_w
    grad[n : 2 * n] = (np.bincount(ai, g_lam, n) + np.bincount(hi, g_mu, n)) / total_w
    grad[2 * n] = -g_lam.sum() / total_w
    grad[2 * n + 1] = -(w * dt_rho).sum() / total_w

    # Ridge: tira verso la media le squadre con poche partite. È in "partite equivalenti" (diviso per il
    # peso totale come la verosimiglianza), così vale lo stesso con 500 o 5.000 partite.
    # Vincolo morbido: somma attacchi = 0.
    value += ridge * (att @ att + dfc @ dfc) / total_w + att.sum() ** 2
    grad[:n] += 2 * ridge * att / total_w + 2 * att.sum()
    grad[n : 2 * n] += 2 * ridge * dfc / total_w
    return value, grad


def fit_dixon_coles(
    home_teams: Sequence[Hashable],
    away_teams: Sequence[Hashable],
    home_goals: Sequence[int],
    away_goals: Sequence[int],
    weights: Sequence[float] | None = None,
    ridge: float = 0.0,
) -> DixonColesFit:
    """Stima attacchi, difese, fattore campo e rho per massima verosimiglianza pesata."""
    teams = tuple(sorted(set(home_teams) | set(away_teams)))
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([index[t] for t in home_teams])
    ai = np.array([index[t] for t in away_teams])
    hg = np.asarray(home_goals, dtype=float)
    ag = np.asarray(away_goals, dtype=float)
    w = np.ones(len(hg)) if weights is None else np.asarray(weights, dtype=float)
    if len(hg) == 0 or w.sum() <= 0:
        raise ValueError("Servono partite con peso positivo per stimare il modello")

    start = np.zeros(2 * n + 2)
    start[2 * n] = np.log(max(np.average(hg, weights=w), 0.1) / max(np.average(ag, weights=w), 0.1))
    bounds = [(None, None)] * (2 * n + 1) + [RHO_BOUNDS]
    res = minimize(_objective, start, args=(n, hi, ai, hg, ag, w, ridge), jac=True, method="L-BFGS-B", bounds=bounds)

    att, dfc = res.x[:n].copy(), res.x[n : 2 * n].copy()
    shift = att.mean()  # centratura esatta: λ e μ non cambiano spostando attacchi e difese insieme
    return DixonColesFit(
        teams=teams,
        attack=att - shift,
        defence=dfc - shift,
        home_advantage=float(res.x[2 * n]),
        rho=float(res.x[2 * n + 1]),
        n_matches=int((w > 0).sum()),
        converged=bool(res.success),
    )
