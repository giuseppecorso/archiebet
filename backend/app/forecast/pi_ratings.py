"""Pi-rating (Constantinou e Fenton 2013, D164): la forza di ogni squadra in casa e in trasferta. Funzioni pure.

Differenza reti attesa = ψ(forza in casa della squadra di casa) − ψ(forza in trasferta dell'ospite), con
ψ(r) = segno(r) · (10^(|r|/3) − 1). Dopo la partita l'errore si comprime (3 · log10(1 + errore)), si applica con passo
λ alla forza giocata e una parte γ della correzione passa anche all'altra forza della stessa squadra.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

BASE, SCALE = 10.0, 3.0
LEARNING = 0.035  # λ del lavoro originale
CROSS = 0.7  # γ del lavoro originale


def psi(r: float) -> float:
    return math.copysign(BASE ** (abs(r) / SCALE) - 1, r)


@dataclass(frozen=True)
class PiState:
    home_h: float  # forza in casa della squadra di casa
    home_a: float  # forza in trasferta della squadra di casa
    away_h: float
    away_a: float
    expected_diff: float  # differenza reti attesa


class PiRatings:
    def __init__(self) -> None:
        self.home: dict[int, float] = defaultdict(float)
        self.away: dict[int, float] = defaultdict(float)

    def state(self, home: int, away: int) -> PiState:
        hh, ha, ah, aa = self.home[home], self.away[home], self.home[away], self.away[away]
        return PiState(hh, ha, ah, aa, psi(hh) - psi(aa))

    def update(self, home: int, away: int, home_goals: int, away_goals: int) -> None:
        expected = psi(self.home[home]) - psi(self.away[away])
        error = (home_goals - away_goals) - expected
        step = math.copysign(SCALE * math.log10(1 + abs(error)), error) if error else 0.0
        new_hh = self.home[home] + step * LEARNING
        self.away[home] += (new_hh - self.home[home]) * CROSS
        self.home[home] = new_hh
        new_aa = self.away[away] - step * LEARNING
        self.home[away] += (new_aa - self.away[away]) * CROSS
        self.away[away] = new_aa
