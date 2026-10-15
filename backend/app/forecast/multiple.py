"""Multipla del giorno (specifiche, sezione 5; regola 7; D68). Funzioni pure, niente database.

Una multipla si gioca su un solo bookmaker: si costruisce separatamente per Sisal e per Eurobet.
- Gambe: al massimo una per partita, probabilità ≥ 65%, quota totale tra 3 e 5, 4 partite (default).
- Prima si cerca la multipla "con valore" (ogni gamba con valore ≥ 0, regola 7); se non c'è, la più facile
  con quote "nella norma" (valore ≥ −5%), dichiarata senza valore. Mai gambe che pagano poco o sospette (> 15%).
- Tra le multiple possibili vince quella con la probabilità di vincere più alta; a parità, valore atteso più alto.
Le partite sono indipendenti tra loro, quindi la probabilità di vincere è il prodotto delle probabilità.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations, product

from app.forecast.clv import SUSPICIOUS_VALUE
from app.forecast.picks import LOW_PRICE

LEGS = 4
MIN_PROBABILITY = 0.65
MIN_TOTAL, MAX_TOTAL = 3.0, 5.0
MAX_MATCHES = 24  # partite più probabili considerate (limita le combinazioni: C(24,4) × 2^4 ≈ 170.000)


@dataclass(frozen=True)
class Leg:
    match_id: int
    kickoff_at: datetime
    market: str
    selection: str
    probability: float
    price: float

    @property
    def value(self) -> float:
        return self.probability * self.price - 1.0


@dataclass(frozen=True)
class Multiple:
    legs: tuple[Leg, ...]  # in ordine di calcio d'inizio
    with_value: bool  # True = ogni gamba con valore ≥ 0

    @property
    def price(self) -> float:
        return math.prod(leg.price for leg in self.legs)

    @property
    def win_probability(self) -> float:
        return math.prod(leg.probability for leg in self.legs)

    @property
    def alive_before_last(self) -> float:
        """Probabilità di arrivare all'ultima partita con la schedina ancora viva."""
        return math.prod(leg.probability for leg in self.legs[:-1])

    @property
    def expected_value(self) -> float:
        """Valore atteso per euro giocato: probabilità di vincere × quota − 1."""
        return self.win_probability * self.price - 1.0

    @property
    def one_in(self) -> float:
        """Vinci circa 1 volta su N."""
        return 1.0 / self.win_probability


@dataclass(frozen=True)
class Profile:
    """Come costruire la multipla (regola 7: prudente, equilibrata, coraggiosa)."""

    min_probability: float
    min_total: float
    max_total: float
    by_value: bool  # True = vince il valore atteso più alto; False = la probabilità di vincere più alta


PROFILES = {
    "tranquilla": Profile(0.70, 2.0, 3.5, by_value=False),
    "equilibrata": Profile(MIN_PROBABILITY, MIN_TOTAL, MAX_TOTAL, by_value=False),  # la multipla del giorno
    "coraggiosa": Profile(0.45, 5.0, 15.0, by_value=True),
}
MAX_COMBINATIONS = 400_000  # tiene la ricerca sotto il secondo anche con 6 partite


def eligible(leg: Leg, min_value: float, min_probability: float = MIN_PROBABILITY) -> bool:
    return leg.probability >= min_probability and min_value <= leg.value <= SUSPICIOUS_VALUE


def _options(legs: Sequence[Leg]) -> list[Leg]:
    """Le gambe da provare per una partita: la più probabile e quella con più valore."""
    best_p = max(legs, key=lambda leg: (leg.probability, leg.value))
    best_v = max(legs, key=lambda leg: (leg.value, leg.probability))
    return [best_p] if best_p == best_v else [best_p, best_v]


def _max_matches(n: int) -> int:
    """Quante partite considerare perché combinazioni × scelte per partita restino sotto il limite."""
    k = n
    while k < MAX_MATCHES and math.comb(k + 1, n) * 2**n <= MAX_COMBINATIONS:
        k += 1
    return k


def _search(legs: Sequence[Leg], min_value: float, n: int, profile: Profile) -> Multiple | None:
    by_match: dict[int, list[Leg]] = {}
    for leg in legs:
        if eligible(leg, min_value, profile.min_probability):
            by_match.setdefault(leg.match_id, []).append(leg)
    if len(by_match) < n:
        return None
    options = {m: _options(ls) for m, ls in by_match.items()}
    rank = (lambda m: max(leg.value for leg in options[m])) if profile.by_value else (lambda m: max(leg.probability for leg in options[m]))
    top = sorted(options, key=rank, reverse=True)[: _max_matches(n)]

    best: tuple[float, float, tuple[Leg, ...]] | None = None
    for matches in combinations(top, n):
        for choice in product(*(options[m] for m in matches)):
            price = math.prod(leg.price for leg in choice)
            if not (profile.min_total <= price <= profile.max_total):
                continue
            p = math.prod(leg.probability for leg in choice)
            ev = p * price - 1.0
            key = (round(ev, 6), p) if profile.by_value else (round(p, 6), ev)
            if best is None or key > best[:2]:
                best = (key[0], key[1], choice)
    if best is None:
        return None
    ordered = tuple(sorted(best[2], key=lambda leg: (leg.kickoff_at, leg.match_id)))
    return Multiple(ordered, with_value=min_value >= 0)


def build_multiple(legs: Sequence[Leg], n: int = LEGS, profile: Profile = PROFILES["equilibrata"]) -> Multiple | None:
    """La multipla migliore per il profilo: prima con valore, altrimenti con quote nella norma."""
    return _search(legs, 0.0, n, profile) or _search(legs, LOW_PRICE, n, profile)


def multiple_of_the_day(legs: Sequence[Leg]) -> Multiple | None:
    """La più facile e sensata (specifiche, sezione 5): profilo equilibrato, 4 partite."""
    return build_multiple(legs)
