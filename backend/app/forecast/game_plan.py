"""Piano partita live (Fase 8, D124, sperimentale): quote minime da giocare nelle situazioni tipiche, calcolate prima.

Stesso motore del termometro live (D92): gol attesi dalla stima migliore, Poisson per squadra, 45% dei gol nel
primo tempo. Quota minima = quota giusta × (1 + soglia D72 per quella quota), solo fino a quota 4.
"""

from dataclasses import dataclass

from app.forecast.live import outcome_probabilities, remaining_rates
from app.forecast.radar import MAX_PRICE, required_value
from app.forecast.simulator import state_share

# (minuto, gol casa, gol ospite)
STATES = (
    (30, 0, 0), (45, 0, 0), (60, 0, 0), (75, 0, 0),
    (45, 1, 0), (45, 0, 1), (60, 1, 0), (60, 0, 1), (75, 1, 0), (75, 0, 1),
    (60, 1, 1),
)  # fmt: skip
SELECTIONS = (("1X2", "1"), ("1X2", "X"), ("1X2", "2"), ("OU2.5", "over"), ("OU2.5", "under"), ("GG", "yes"), ("GG", "no"))


@dataclass(frozen=True)
class PlanLine:
    market: str
    selection: str
    probability: float
    fair_odds: float
    min_odds: float | None  # None: quota oltre 4 o esito già deciso, non si gioca


@dataclass(frozen=True)
class PlanState:
    minute: int
    home_goals: int
    away_goals: int
    remaining: tuple[float, float]  # gol attesi da qui alla fine
    lines: list[PlanLine]


def min_odds(fair: float) -> float | None:
    """Quota sotto la quale non c'è abbastanza valore (D72), o None se la quota giusta supera il tetto di 4."""
    if fair > MAX_PRICE:
        return None
    price = fair
    for _ in range(20):  # la soglia dipende dalla quota stessa: punto fisso, converge in pochi passi
        price = fair * (1 + required_value(price))
    return round(price, 2)


def plan(rates: tuple[float, float], states: tuple[tuple[int, int, int], ...] = STATES) -> list[PlanState]:
    out = []
    for minute, h, a in states:
        rem = remaining_rates(rates, state_share(minute), h, a)
        probs = outcome_probabilities(rem[0], rem[1], h, a)
        lines = []
        for market, sel in SELECTIONS:
            p = probs[sel] if sel in probs else 1.0 - probs["over" if sel == "under" else "yes"]
            if p < 0.01 or p > 0.99:  # esito quasi deciso: niente quota sensata
                continue
            fair = 1 / p
            lines.append(PlanLine(market, sel, p, round(fair, 2), min_odds(fair)))
        out.append(PlanState(minute, h, a, rem, lines))
    return out
