"""Termometro della speranza (Fase 5, D92): probabilità di ogni esito e della schedina durante la partita.

Modello (sulla scia di Dixon & Robinson 1998, "A birth process model for association football matches"):
- prima della partita i gol di casa e ospite sono due Poisson con medie λ_casa e λ_ospite, scelte perché le
  probabilità 1X2 (e Under/Over 2.5, se c'è) coincidano con quelle giuste del mercato;
- durante la partita i gol che restano sono Poisson con le stesse medie moltiplicate per la parte di partita che
  resta; nel secondo tempo si segna di più che nel primo (quota del primo tempo misurata sui dati: FIRST_HALF_SHARE);
- contano solo i 90 minuti più recupero, come nei mercati che seguiamo (i supplementari no).
Solo informazione per chi segue le sue giocate: nessun consiglio di giocare live (specifiche, principio 8).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from scipy.optimize import minimize

from app.forecast.radar_markets import is_secondary

MAX_GOALS = 12
FIRST_HALF_SHARE = 0.45  # quota dei gol segnati nel primo tempo: stimata con `python -m app.cli live-check` (D92)
STOPPAGE_MINUTES = 3.0  # recupero medio che resta quando il cronometro segna 90'
# Gol che restano secondo il punteggio (D93): chi è avanti, chi è indietro, in parità. 1 = nessun effetto.
NO_SCORE_EFFECT = {"leader": 1.0, "trailer": 1.0, "level": 1.0}
SCORE_EFFECT = dict(NO_SCORE_EFFECT)


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def score_matrix(lam_home: float, lam_away: float, n: int = MAX_GOALS) -> list[list[float]]:
    """P(gol casa = i, gol ospite = j) con Poisson indipendenti."""
    ph = [poisson(i, lam_home) for i in range(n)]
    pa = [poisson(j, lam_away) for j in range(n)]
    return [[ph[i] * pa[j] for j in range(n)] for i in range(n)]


def outcome_probabilities(lam_home: float, lam_away: float, home_goals: int = 0, away_goals: int = 0) -> dict[str, float]:
    """Probabilità finali di 1, X, 2, Over 2.5 ("over"), Over 0.5, 1.5, 3.5 e 4.5 ("over0.5", ...) e Goal
    partendo dal punteggio attuale e dai gol che restano."""
    out = {"1": 0.0, "X": 0.0, "2": 0.0, "over": 0.0, **{f"over{n}.5": 0.0 for n in (0, 1, 3, 4)}, "yes": 0.0}
    matrix = score_matrix(lam_home, lam_away)
    total = sum(map(sum, matrix))  # oltre 12 gol resta una probabilità minuscola: si rinormalizza
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            p /= total
            h, a = home_goals + i, away_goals + j
            out["1" if h > a else "X" if h == a else "2"] += p
            out["over"] += p if h + a >= 3 else 0.0
            for n in (0, 1, 3, 4):
                out[f"over{n}.5"] += p if h + a > n else 0.0
            out["yes"] += p if h > 0 and a > 0 else 0.0
    return out


def fit_rates(p1: float, p2: float, p_over: float | None = None) -> tuple[float, float]:
    """Gol attesi (casa, ospite) che riproducono le probabilità del mercato (minimi quadrati, in scala logaritmica)."""

    def loss(x):
        o = outcome_probabilities(math.exp(x[0]), math.exp(x[1]))
        err = (o["1"] - p1) ** 2 + (o["2"] - p2) ** 2
        return err + ((o["over"] - p_over) ** 2 if p_over is not None else 0.0)

    res = minimize(loss, x0=[math.log(1.4), math.log(1.1)], method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-10})
    return math.exp(res.x[0]), math.exp(res.x[1])


def remaining_share(status: str, minute: int | None, first_half: float = FIRST_HALF_SHARE) -> float:
    """Che parte dei gol attesi della partita resta da giocare (0 a fine partita)."""
    second_half = 1.0 - first_half
    m = float(minute or 0)
    if status in ("NS", "TBD"):
        return 1.0
    if status == "1H":
        return first_half * max(45.0 - m, STOPPAGE_MINUTES / 2) / 45.0 + second_half
    if status == "HT":
        return second_half
    if status in ("2H", "LIVE", "SUSP", "INT"):
        return second_half * max(90.0 - m, STOPPAGE_MINUTES) / 45.0
    return 0.0  # finita, o supplementari / rigori: per i nostri mercati conta il 90'


def remaining_rates(rates: tuple[float, float], share: float, home_goals: int, away_goals: int,
                    effect: Mapping[str, float] = SCORE_EFFECT) -> tuple[float, float]:
    """Gol attesi da qui alla fine per casa e ospite, corretti per il punteggio (D93)."""
    if home_goals > away_goals:
        mh, ma = effect["leader"], effect["trailer"]
    elif home_goals < away_goals:
        mh, ma = effect["trailer"], effect["leader"]
    else:
        mh = ma = effect["level"]
    return rates[0] * share * mh, rates[1] * share * ma


def selection_probability(market: str, pick: str, probs: Mapping[str, float]) -> float:
    """Probabilità di un esito di un mercato da quelle finali (1, X, 2, over, yes)."""
    if market == "1X2":
        return probs[pick]
    if market == "DC":
        return sum(probs[s] for s in pick if s in ("1", "X", "2")) if pick in ("1X", "12", "X2") else 0.0
    if market in ("OU0.5", "OU1.5", "OU2.5", "OU3.5", "OU4.5"):
        key = "over" if market == "OU2.5" else f"over{market[2:]}"
        return probs[key] if pick == "over" else 1.0 - probs[key]
    if market == "GG":
        return probs["yes"] if pick == "yes" else 1.0 - probs["yes"]
    raise ValueError(market)


@dataclass(frozen=True)
class LegState:
    market: str
    pick: str
    rates: tuple[float, float] | None  # gol attesi prima della partita; None = non noti
    status: str  # "NS", "1H", "HT", "2H", ..., "FT"
    minute: int | None
    home_goals: int
    away_goals: int
    settled: bool | None = None  # True vinta, False persa, None in corso o da giocare


def leg_probability(leg: LegState) -> float | None:
    """Probabilità che la gamba vinca adesso; None se mancano i gol attesi (niente quote prima della partita)."""
    if leg.settled is not None:
        return 1.0 if leg.settled else 0.0
    if leg.rates is None or is_secondary(leg.market):
        return None  # angoli e cartellini: niente modello dal vivo
    share = remaining_share(leg.status, leg.minute)
    lh, la = remaining_rates(leg.rates, share, leg.home_goals, leg.away_goals)
    probs = outcome_probabilities(lh, la, leg.home_goals, leg.away_goals)
    return selection_probability(leg.market, leg.pick, probs)


def bet_probability(legs: Sequence[LegState]) -> float | None:
    """Termometro della schedina: prodotto delle gambe (partite diverse, indipendenti)."""
    out = 1.0
    for leg in legs:
        p = leg_probability(leg)
        if p is None:
            return None
        out *= p
    return out
