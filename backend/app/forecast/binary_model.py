"""Ricalibrazione di un mercato a due esiti (es. Under/Over 2.5) con fattori, per la prova del nove (D76).

logit(p) = a · logit(p_apertura) + b + Σ βₖ · xₖ, stimata con le sole stagioni precedenti (walk-forward).
È la versione a due esiti di market_model (1X2, D56): stessa penalità L2 sui parametri diversi da a.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

L2 = 1e-4


@dataclass(frozen=True)
class BinaryRow:
    match_id: int
    season: str
    outcome: int  # 1 = è uscito l'esito (es. Over), 0 = no
    p_open: float  # probabilità giusta di apertura dell'esito


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _design(p_open: np.ndarray, features: np.ndarray) -> np.ndarray:
    return np.column_stack([_logit(p_open), np.ones(len(p_open)), features])


def _nll(theta: np.ndarray, x: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    p = 1 / (1 + np.exp(-(x @ theta)))
    p = np.clip(p, 1e-12, 1 - 1e-12)
    value = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)) + L2 * (theta[1:] @ theta[1:])
    grad = x.T @ (p - y) / len(y)
    grad[1:] += 2 * L2 * theta[1:]
    return value, grad


def fit(p_open: np.ndarray, features: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    x = _design(p_open, features)
    start = np.zeros(x.shape[1])
    start[0] = 1.0  # si parte dal mercato così com'è
    return minimize(_nll, start, args=(x, outcomes.astype(float)), jac=True, method="L-BFGS-B").x


def predict(theta: np.ndarray, p_open: np.ndarray, features: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(_design(p_open, features) @ theta)))


def walk_forward_by_season(
    rows: Sequence[BinaryRow], features: Mapping[int, Sequence[float]], eval_seasons: Sequence[str], n_features: int
) -> dict[int, float]:
    """Probabilità corrette delle partite delle stagioni valutate, stimate con le sole stagioni precedenti."""
    out: dict[int, float] = {}
    for season in sorted(eval_seasons):
        train = [r for r in rows if r.season < season]
        test = [r for r in rows if r.season == season]
        if not train or not test:
            continue

        def arrays(rs):
            p = np.array([r.p_open for r in rs])
            x = np.array([features.get(r.match_id, [0.0] * n_features) for r in rs], dtype=float).reshape(len(rs), n_features)
            return p, x

        p_tr, x_tr = arrays(train)
        theta = fit(p_tr, x_tr, np.array([r.outcome for r in train]))
        p_te, x_te = arrays(test)
        for r, prob in zip(test, predict(theta, p_te, x_te)):
            out[r.match_id] = float(prob)
    return out
