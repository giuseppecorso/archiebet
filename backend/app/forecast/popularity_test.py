"""Prova del "tifo" dei bookmaker (D78, ipotesi 6): bet365 paga meno del giusto le squadre popolari?

Per ogni partita e per le due vittorie (1 e 2): valore = probabilità giusta (Pinnacle d'apertura, Shin) × quota
bet365 d'apertura − 1. Regressione: valore ~ costante + logit(probabilità) + "squadra popolare" + "avversaria di
una popolare". Il logit tiene conto del favourite-longshot bias (a parità di probabilità si confronta il simile).
Ipotesi: coefficiente "popolare" < 0 e "avversaria" > 0, oltre 2 errori standard, sia fino al 2024/25 sia nel 2025/26.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

POPULAR = {
    "Juventus", "Inter", "Milan", "Napoli", "Roma",
    "Man United", "Liverpool", "Arsenal", "Chelsea", "Man City",
    "Real Madrid", "Barcelona", "Bayern Munich", "Dortmund", "Paris SG", "Marseille",
}  # fmt: skip
LEAGUES = ("ITA-A", "ENG-1", "ESP-1", "GER-1", "FRA-1")


@dataclass(frozen=True)
class ValueRow:
    season: str
    probability: float  # probabilità giusta della vittoria
    value: float  # valore della quota bet365 per quella vittoria
    popular: bool  # la squadra che deve vincere è popolare
    against_popular: bool  # l'avversaria è popolare (e questa no)


@dataclass(frozen=True)
class Coefficient:
    estimate: float
    std_error: float


@dataclass(frozen=True)
class PopularityResult:
    n: int
    popular: Coefficient  # quanto valore in più/meno sulle popolari (atteso < 0)
    against_popular: Coefficient  # e sulle loro avversarie (atteso > 0)

    @property
    def confirmed(self) -> bool:
        return self.popular.estimate < -2 * self.popular.std_error and self.against_popular.estimate > 2 * self.against_popular.std_error


def regress(rows: Sequence[ValueRow]) -> PopularityResult:
    """Minimi quadrati con errori standard robusti (HC1: non assumono la stessa varianza per ogni quota)."""
    p = np.clip(np.array([r.probability for r in rows]), 1e-6, 1 - 1e-6)
    x = np.column_stack([np.ones(len(rows)), np.log(p / (1 - p)), [r.popular for r in rows], [r.against_popular for r in rows]]).astype(float)
    y = np.array([r.value for r in rows])
    xtx_inv = np.linalg.inv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    resid = y - x @ beta
    n, k = x.shape
    cov = xtx_inv @ (x.T * resid**2) @ x @ xtx_inv * n / (n - k)
    se = np.sqrt(np.diag(cov))
    return PopularityResult(n, Coefficient(float(beta[2]), float(se[2])), Coefficient(float(beta[3]), float(se[3])))


def value_rows(season: str, home: str, away: str, fair: Sequence[float], bet365: Sequence[float]) -> list[ValueRow]:
    """Le due vittorie di una partita (il pareggio non ha una squadra "popolare")."""
    out = []
    for team, other, p, price in ((home, away, fair[0], bet365[0]), (away, home, fair[2], bet365[2])):
        if price > 1 and 0 < p < 1:
            out.append(ValueRow(season, p, p * price - 1.0, team in POPULAR, other in POPULAR and team not in POPULAR))
    return out


def describe(c: Coefficient) -> str:
    return f"{c.estimate:+.4f} ± {c.std_error:.4f} ({c.estimate / c.std_error:+.1f} errori standard)" if c.std_error > 0 and not math.isnan(c.std_error) else "n.d."
