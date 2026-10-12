"""Misure di qualità delle previsioni (principio 2: si giudica la calibrazione, non i soldi vinti).

Per l'1X2 le probabilità sono una matrice (n, 3) nell'ordine 1, X, 2 e gli esiti sono indici 0, 1, 2.
Più bassi sono log loss, Brier e RPS, migliori sono le previsioni.
"""

from dataclasses import dataclass

import numpy as np

_EPS = 1e-15  # evita log(0) se una probabilità è esattamente zero


def outcome_index(home_goals: int, away_goals: int) -> int:
    return 0 if home_goals > away_goals else 1 if home_goals == away_goals else 2


def _one_hot(outcomes: np.ndarray, k: int) -> np.ndarray:
    return np.eye(k)[np.asarray(outcomes)]


def log_loss(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Media di −log(probabilità data all'esito che si è verificato)."""
    p = np.asarray(probs)[np.arange(len(outcomes)), outcomes]
    return float(-np.log(np.clip(p, _EPS, 1.0)).mean())


def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Media della somma dei quadrati degli errori su tutti gli esiti (da 0 a 2)."""
    probs = np.asarray(probs)
    return float(((probs - _one_hot(outcomes, probs.shape[1])) ** 2).sum(axis=1).mean())


def rps(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Ranked Probability Score: come il Brier, ma sbagliare 1 per 2 costa più che 1 per X."""
    probs = np.asarray(probs)
    diff = np.cumsum(probs - _one_hot(outcomes, probs.shape[1]), axis=1)[:, :-1]
    return float((diff**2).sum(axis=1).mean() / (probs.shape[1] - 1))


@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    count: int
    predicted: float  # probabilità media prevista nella fascia
    observed: float  # frequenza con cui l'evento si è verificato davvero


def calibration(predicted: np.ndarray, happened: np.ndarray, bins: int = 10) -> list[CalibrationBin]:
    """Fasce di probabilità prevista: un modello calibrato ha predicted ≈ observed in ogni fascia."""
    predicted, happened = np.asarray(predicted, dtype=float), np.asarray(happened, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(predicted, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        mask = idx == b
        if mask.any():
            out.append(
                CalibrationBin(float(edges[b]), float(edges[b + 1]), int(mask.sum()), float(predicted[mask].mean()), float(happened[mask].mean()))
            )
    return out


def expected_calibration_error(table: list[CalibrationBin]) -> float:
    """Scarto medio |previsto − osservato|, pesato per il numero di casi in ogni fascia."""
    total = sum(b.count for b in table)
    return sum(b.count * abs(b.predicted - b.observed) for b in table) / total if total else 0.0
