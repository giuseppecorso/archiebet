"""Arrivare a un moltiplicatore scelto spendendo meno (D176-D177). Funzioni pure.

Per ogni giorno si cerca la combinazione di partite diverse che sta nell'intervallo con il punteggio più alto. Si usano
solo 1X2 e Under/Over 2.5: sono i mercati con una quota di un bookmaker e un prezzo giusto di Pinnacle da confrontare.
"""

import math
from collections.abc import Sequence
from itertools import combinations

from app.forecast.radar import BookOdds, scan

LOW, HIGH = 6.0, 10.0
CENTER = 8.0  # dove si punta dentro l'intervallo 6-10
BAND = 1.25  # ogni partita può stare fino a questo fattore sopra o sotto la quota che le spetterebbe
TOP = 12  # le partite migliori tra cui si cercano le combinazioni
MARKETS = ("1X2", "OU2.5")
SHARP = ("pinnacle",)


def score(row: dict, target: float, mode: str) -> float:
    """Più alto è meglio. Nessun risultato entra qui."""
    if mode == "vicine":
        return -abs(math.log(row["price"] / target))
    if mode == "valore":
        return row["price"] * row["sharp"] - 1
    raise ValueError(mode)


def best_slip(rows: Sequence[dict], legs: int, mode: str, low: float = LOW, high: float = HIGH, center: float | None = None) -> list[dict] | None:
    """La combinazione di `legs` partite diverse con il moltiplicatore nell'intervallo e il punteggio più alto."""
    middle = center if center is not None else (CENTER if (low, high) == (LOW, HIGH) else math.sqrt(low * high))
    target = middle ** (1 / legs)
    bottom, top = (low, high) if legs == 1 else (target / BAND, target * BAND)
    per_match: dict[int, dict] = {}
    for row in rows:
        if bottom <= row["price"] <= top:
            current = per_match.get(row["match_id"])
            if current is None or score(row, target, mode) > score(current, target, mode):
                per_match[row["match_id"]] = row
    pool = sorted(per_match.values(), key=lambda r: (-score(r, target, mode), r["match_id"]))[:TOP]
    best, best_score = None, -math.inf
    for combo in combinations(pool, legs):
        if low <= math.prod(r["price"] for r in combo) <= high:
            total = sum(score(r, target, mode) for r in combo)
            if total > best_score:
                best, best_score = list(combo), total
    return best


def price_rows(match_id: int, when: str, book: BookOdds, playable: Sequence[str]) -> list[dict]:
    """Gli esiti di una partita con la miglior quota giocabile e la probabilità giusta di Pinnacle."""
    return [{"match_id": match_id, "when": when, "market": c.market, "selection": c.selection, "price": c.price, "sharp": c.fair_probability}
            for c in scan(book, playable=playable, sharp=SHARP, all_outcomes=True) if c.market in MARKETS and not c.suspicious]  # fmt: skip


def legs_for(center: float) -> int:
    """Quante partite con «Decide Archie»: poche, ogni partita in più paga di nuovo il margine (Whelan 2026, D174)."""
    return 2 if center <= 12 else 3 if center <= 40 else 4
