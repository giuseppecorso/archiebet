"""Mercati ricavati dalla matrice dei risultati: tutti coerenti tra loro (regola di decisione 1).

Le chiavi sono le stesse di `app.betting.calc.MARKETS` ("1X2", "DC", "OU2.5", "GG"); in più le
altre linee Under/Over ("OU0.5" ... "OU4.5").
"""

import numpy as np

OU_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)


def outcome_1x2(m: np.ndarray) -> dict[str, float]:
    home = float(np.tril(m, -1).sum())  # sotto la diagonale: gol casa > gol fuori
    draw = float(np.trace(m))
    return {"1": home, "X": draw, "2": float(m.sum()) - home - draw}


def markets(m: np.ndarray) -> dict[str, dict[str, float]]:
    """Probabilità di ogni esito per ogni mercato, a partire da P[gol casa, gol fuori]."""
    p = outcome_1x2(m)
    out = {
        "1X2": p,
        "DC": {"1X": p["1"] + p["X"], "X2": p["X"] + p["2"], "12": p["1"] + p["2"]},
    }
    goals = np.add.outer(np.arange(m.shape[0]), np.arange(m.shape[1]))
    for line in OU_LINES:
        under = float(m[goals < line].sum())
        out[f"OU{line}"] = {"over": 1.0 - under, "under": under}
    no_goal = float(m[0, :].sum() + m[:, 0].sum() - m[0, 0])
    out["GG"] = {"yes": 1.0 - no_goal, "no": no_goal}
    return out


def fair_price(probability: float) -> float | None:
    """Quota giusta = 1 / probabilità (nessuna quota se l'evento è impossibile)."""
    return 1.0 / probability if probability > 0 else None


def value(probability: float, price: float) -> float:
    """Valore = probabilità × quota − 1 (principio 1). Positivo = la quota paga più del dovuto."""
    return probability * price - 1.0
