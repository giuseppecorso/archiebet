"""Banco di prova contro il mercato (D53): il mercato è la base, un fattore entra solo se lo corregge in meglio.

Modello: regressione logistica multinomiale sulle probabilità di apertura senza margine.
  punteggio(1) = a·log p1 + b1 + Σ β1·fattore
  punteggio(X) = a·log pX                      (riferimento)
  punteggio(2) = a·log p2 + b2 + Σ β2·fattore
  probabilità = softmax dei punteggi
Con a = 1 e il resto a 0 si riottengono esattamente le probabilità del mercato. "a" e "b" correggono
le distorsioni sistematiche delle quote (es. favoriti/sfavoriti), i β dicono quanto conta il fattore.
Si stima ogni stagione con le sole stagioni precedenti (walk-forward) e si confronta con e senza fattore.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

L2 = 1e-3  # piccola spinta verso zero dei coefficienti, per stabilità


@dataclass(frozen=True)
class MarketRow:
    match_id: int
    season: str
    outcome: int  # 0 = 1, 1 = X, 2 = 2
    p_open: tuple[float, float, float]  # apertura senza margine


def _design(p_open: np.ndarray, features: np.ndarray) -> np.ndarray:
    """Matrice (parametri, partite, 3 esiti): il punteggio è la somma dei parametri per queste colonne."""
    n, f = features.shape
    zero = np.zeros(n)
    cols = [np.log(p_open)]  # a
    cols.append(np.stack([np.ones(n), zero, zero], axis=1))  # b1
    cols.append(np.stack([zero, zero, np.ones(n)], axis=1))  # b2
    for k in range(f):
        cols.append(np.stack([features[:, k], zero, zero], axis=1))  # β1
        cols.append(np.stack([zero, zero, features[:, k]], axis=1))  # β2
    return np.stack(cols)


def _softmax(scores: np.ndarray) -> np.ndarray:
    e = np.exp(scores - scores.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _nll(theta: np.ndarray, design: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    probs = _softmax(np.tensordot(theta, design, axes=1))
    n = len(y)
    value = -np.log(probs[np.arange(n), y]).mean() + L2 * (theta[1:] @ theta[1:])
    resid = probs - np.eye(3)[y]  # derivata della log loss rispetto ai punteggi
    grad = np.tensordot(design, resid, axes=([1, 2], [0, 1])) / n
    grad[1:] += 2 * L2 * theta[1:]
    return value, grad


def fit(p_open: np.ndarray, features: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    design = _design(p_open, features)
    start = np.zeros(design.shape[0])
    start[0] = 1.0  # si parte dal mercato così com'è
    return minimize(_nll, start, args=(design, outcomes), jac=True, method="L-BFGS-B").x


def predict(theta: np.ndarray, p_open: np.ndarray, features: np.ndarray) -> np.ndarray:
    return _softmax(np.tensordot(theta, _design(p_open, features), axes=1))


def walk_forward_by_season(
    rows: Sequence[MarketRow], features: Mapping[int, Sequence[float]], eval_seasons: Sequence[str], n_features: int
) -> dict[int, np.ndarray]:
    """Probabilità corrette per le partite delle stagioni valutate, stimate con le sole stagioni precedenti."""
    out: dict[int, np.ndarray] = {}
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
        for r, probs in zip(test, predict(theta, p_te, x_te)):
            out[r.match_id] = probs
    return out
