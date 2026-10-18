"""Metodi per togliere il margine del bookmaker e ricavare le probabilità giuste (D72).

Le probabilità implicite (1/quota) sommano più di 1: la differenza è il margine. Tre modi di toglierlo:
- proporzionale: ogni probabilità divisa per la somma (margine distribuito uguale su tutti gli esiti);
- power: p = (1/quota)^k con k scelto perché la somma sia 1 (toglie di più agli sfavoriti);
- Shin (1993): modello con una quota di scommettitori "informati"; toglie di più agli sfavoriti
  (Štrumbelj 2014, "On determining probability forecasts from betting odds");
- additivo: la stessa quantità tolta a ogni esito (se uno sfavorito andrebbe sotto zero, non si applica);
- odds ratio (Cheung 2015): il rapporto tra le quote "vere" e quelle del bookmaker è lo stesso per ogni esito.
Gli ultimi due correggono il favourite-longshot bias: i bookmaker caricano più margine sulle quote alte.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Method = Callable[[Sequence[float]], tuple[float, ...]]


def _bisect(f: Callable[[float], float], low: float, high: float, tol: float = 1e-12) -> float:
    """Radice di una funzione decrescente in [low, high]."""
    for _ in range(200):
        mid = (low + high) / 2
        if f(mid) > 0:
            low = mid
        else:
            high = mid
        if high - low < tol:
            break
    return (low + high) / 2


def proportional(prices: Sequence[float]) -> tuple[float, ...]:
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    return tuple(x / total for x in implied)


def power(prices: Sequence[float]) -> tuple[float, ...]:
    implied = [1.0 / p for p in prices]
    if sum(implied) <= 1.0:  # nessun margine (o quote da exchange): niente da togliere
        return proportional(prices)
    k = _bisect(lambda k: sum(x**k for x in implied) - 1.0, 1.0, 20.0)
    probs = [x**k for x in implied]
    total = sum(probs)
    return tuple(p / total for p in probs)


def shin(prices: Sequence[float]) -> tuple[float, ...]:
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    if total <= 1.0:
        return proportional(prices)

    def probs(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4 * (1 - z) * x * x / total) - z) / (2 * (1 - z)) for x in implied]

    z = _bisect(lambda z: sum(probs(z)) - 1.0, 0.0, 0.99)
    p = probs(z)
    s = sum(p)
    return tuple(x / s for x in p)


def additive(prices: Sequence[float]) -> tuple[float, ...]:
    implied = [1.0 / p for p in prices]
    cut = (sum(implied) - 1.0) / len(implied)
    probs = [x - cut for x in implied]
    if min(probs) <= 0:  # sfavorito troppo lontano: il metodo non regge, si usa il proporzionale
        return proportional(prices)
    return tuple(probs)


def odds_ratio(prices: Sequence[float]) -> tuple[float, ...]:
    implied = [1.0 / p for p in prices]
    if sum(implied) <= 1.0:
        return proportional(prices)

    def probs(c: float) -> list[float]:
        return [x / (c - c * x + x) for x in implied]  # p/(1−p) = (x/(1−x)) / c

    c = _bisect(lambda c: sum(probs(c)) - 1.0, 1.0, 50.0)
    p = probs(c)
    s = sum(p)
    return tuple(x / s for x in p)


METHODS: dict[str, Method] = {
    "proporzionale": proportional,
    "additivo": additive,
    "power": power,
    "shin": shin,
    "odds ratio": odds_ratio,
}


# ---------- Prova del nove dei metodi (D72) ----------


@dataclass(frozen=True)
class MethodScore:
    name: str
    n: int
    log_loss: float
    diff_vs_proportional: float  # log loss del metodo − proporzionale (negativo = meglio)
    diff_std_error: float
    longshot_predicted: float  # probabilità media data agli esiti con quota > 4
    longshot_observed: float  # quante volte sono usciti davvero

    @property
    def passes(self) -> bool:
        """Migliora il proporzionale oltre 2 errori standard (stesso criterio delle altre prove del nove)."""
        return self.diff_vs_proportional < -2 * self.diff_std_error


def compare_methods(rows: Sequence[tuple[Sequence[float], int]], longshot_price: float = 4.0) -> list[MethodScore]:
    """rows = (quote del mercato, indice dell'esito uscito). Log loss sui risultati veri, a coppie col proporzionale."""
    losses = {name: [-math.log(max(m(prices)[outcome], 1e-12)) for prices, outcome in rows] for name, m in METHODS.items()}
    base = losses["proporzionale"]
    out = []
    for name, m in METHODS.items():
        diffs = [a - b for a, b in zip(losses[name], base)]
        mean = sum(diffs) / len(diffs)
        var = sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1) if len(diffs) > 1 else 0.0
        long_p, long_hit = [], []
        for prices, outcome in rows:
            probs = m(prices)
            for i, price in enumerate(prices):
                if price > longshot_price:
                    long_p.append(probs[i])
                    long_hit.append(1.0 if i == outcome else 0.0)
        out.append(
            MethodScore(
                name, len(rows), sum(losses[name]) / len(rows), mean, math.sqrt(var / len(diffs)),
                sum(long_p) / len(long_p) if long_p else 0.0, sum(long_hit) / len(long_hit) if long_hit else 0.0,
            )
        )
    return out
