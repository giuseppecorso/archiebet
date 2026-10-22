"""Quote giuste di multigol e combo (D136), ricavate dal mercato. Funzioni pure.

La fonte delle quote non ha multigol e combo di Sisal ed Eurobet: Archie calcola solo la quota giusta, da confrontare a
mano con l'app del bookmaker. Metodo: gol attesi delle due squadre che riproducono 1X2 e Under/Over 2.5 senza margine
(stesso modello di Poisson del termometro live, D92), poi la probabilità di ogni risultato esatto e la somma dei
risultati che fanno vincere la giocata. È una **stima**: il legame tra risultato e numero di gol non è ancora provato
sul passato, e Poisson sottostima un po' i pareggi.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.forecast.live import fit_rates, score_matrix

Score = Callable[[int, int], bool]

MULTIGOL = ((1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (2, 5), (3, 5), (4, 6))


def _result(h: int, a: int) -> str:
    return "1" if h > a else "X" if h == a else "2"


COMBOS: tuple[tuple[str, Score], ...] = (
    ("1 + Over 1.5", lambda h, a: h > a and h + a > 1.5),
    ("1 + Over 2.5", lambda h, a: h > a and h + a > 2.5),
    ("1 + Under 3.5", lambda h, a: h > a and h + a < 3.5),
    ("X + Under 2.5", lambda h, a: h == a and h + a < 2.5),
    ("2 + Over 1.5", lambda h, a: a > h and h + a > 1.5),
    ("2 + Over 2.5", lambda h, a: a > h and h + a > 2.5),
    ("2 + Under 3.5", lambda h, a: a > h and h + a < 3.5),
    ("1X + Over 1.5", lambda h, a: h >= a and h + a > 1.5),
    ("1X + Under 3.5", lambda h, a: h >= a and h + a < 3.5),
    ("X2 + Over 1.5", lambda h, a: a >= h and h + a > 1.5),
    ("X2 + Under 3.5", lambda h, a: a >= h and h + a < 3.5),
    ("12 + Over 2.5", lambda h, a: h != a and h + a > 2.5),
    ("1 + Goal", lambda h, a: h > a and a > 0),
    ("2 + Goal", lambda h, a: a > h and h > 0),
    ("Goal + Over 2.5", lambda h, a: h > 0 and a > 0 and h + a > 2.5),
    ("NoGoal + Under 2.5", lambda h, a: (h == 0 or a == 0) and h + a < 2.5),
)


@dataclass(frozen=True)
class DerivedLine:
    group: str  # "Multigol" | "Combo"
    label: str
    probability: float

    @property
    def fair_odds(self) -> float:
        return 1.0 / self.probability


def probability(matrix: list[list[float]], wins: Score) -> float:
    total = sum(map(sum, matrix))
    return sum(p for h, row in enumerate(matrix) for a, p in enumerate(row) if wins(h, a)) / total


def derived_lines(p1: float, p2: float, p_over: float | None) -> list[DerivedLine]:
    """Multigol e combo con la loro probabilità, dai gol attesi che riproducono il mercato."""
    rates = fit_rates(p1, p2, p_over)
    matrix = score_matrix(*rates)
    out = [DerivedLine("Multigol", f"Multigol {lo}-{hi}", probability(matrix, lambda h, a, lo=lo, hi=hi: lo <= h + a <= hi)) for lo, hi in MULTIGOL]
    out += [DerivedLine("Combo", label, probability(matrix, wins)) for label, wins in COMBOS]
    return [line for line in out if line.probability > 0.01]
