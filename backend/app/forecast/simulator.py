"""Simulatore partita (Fase 6, D115): 10.000 partite simulate dai gol attesi, una partita "dal vivo", comandi "E se...".

I gol attesi vengono dalle probabilità migliori prima della partita (come il termometro, D92). Ogni squadra segna
secondo una Poisson; i minuti dei gol seguono la quota del primo tempo (45%) e del secondo (55%). "E se al 30' sta 1-0?"
riparte da quel minuto e quel punteggio con i gol attesi che restano.
"""

from collections import Counter
from dataclasses import dataclass

import numpy as np

from app.forecast.live import FIRST_HALF_SHARE, remaining_share

N_SIM = 10_000


@dataclass(frozen=True)
class GoalEvent:
    minute: int
    side: str  # "home" | "away"


@dataclass(frozen=True)
class Simulation:
    n: int
    rates: tuple[float, float]  # gol attesi a inizio partita
    remaining: tuple[float, float]  # gol attesi da qui alla fine
    p_home: float
    p_draw: float
    p_away: float
    p_over25: float
    p_gg: float
    avg_goals: tuple[float, float]
    top_scores: list[tuple[int, int, float]]  # (casa, ospite, frequenza)
    sample: list[GoalEvent]  # una partita simulata, gol in ordine di minuto (dal minuto di partenza)


def state_share(minute: int) -> float:
    """Parte dei gol attesi che resta dal minuto indicato (0 = calcio d'inizio, 45 = intervallo, 90 = fine)."""
    if minute <= 0:
        return 1.0
    if minute < 45:
        return remaining_share("1H", minute)
    if minute == 45:
        return remaining_share("HT", 45)
    return remaining_share("2H", min(minute, 90))


def goal_minutes(rng: np.random.Generator, count: int, start: int) -> list[int]:
    """Minuti di `count` gol da `start` in poi: primo tempo 45% dei gol, secondo 55%, uniformi dentro ogni tempo."""
    out = []
    first_left = max(45 - start, 0) / 45 * FIRST_HALF_SHARE
    second_left = (45 if start <= 45 else max(90 - start, 0)) / 45 * (1 - FIRST_HALF_SHARE)
    total = first_left + second_left or 1.0
    for _ in range(count):
        if rng.random() < first_left / total:
            out.append(int(rng.integers(max(start, 0) + 1, 46)))
        else:
            out.append(int(rng.integers(max(start, 45) + 1, 91)) if start < 90 else 90)
    return sorted(out)


def simulate(rates: tuple[float, float], minute: int = 0, score: tuple[int, int] = (0, 0), n: int = N_SIM, seed: int | None = None) -> Simulation:
    rng = np.random.default_rng(seed)
    share = state_share(minute)
    rh, ra = rates[0] * share, rates[1] * share
    home = score[0] + rng.poisson(rh, n)
    away = score[1] + rng.poisson(ra, n)
    total = home + away
    counts = Counter(zip(home.tolist(), away.tolist()))
    top = [(h, a, c / n) for (h, a), c in counts.most_common(6)]
    sh, sa = int(rng.poisson(rh)), int(rng.poisson(ra))
    events = [GoalEvent(m, "home") for m in goal_minutes(rng, sh, minute)] + [GoalEvent(m, "away") for m in goal_minutes(rng, sa, minute)]
    return Simulation(
        n, rates, (rh, ra),
        float((home > away).mean()), float((home == away).mean()), float((home < away).mean()),
        float((total >= 3).mean()), float(((home > 0) & (away > 0)).mean()),
        (float(home.mean()), float(away.mean())), top, sorted(events, key=lambda e: (e.minute, e.side)),
    )  # fmt: skip
