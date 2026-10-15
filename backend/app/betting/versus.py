"""Io contro Archie (Fase 4): le tue giocate giudicate con le probabilità che Archie aveva AL MOMENTO della giocata.

Fonte delle probabilità: la "fotografia" salvata con la schedina (niente senno di poi). Come nei Pronostici (D67):
prima il mercato senza margine, il modello di Archie dove il mercato manca; la doppia chance dall'1X2.

Due domande, con numeri calcolati dal codice:
1. Il tuo fiuto: vinci più spesso di quanto Archie si aspettava? (vinte − attese, con il suo errore standard)
2. Quando Archie era d'accordo (valore ≥ 0 alla tua quota) rendi di più che quando non lo era?
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JudgedPick:
    probability: float  # probabilità di Archie al momento della giocata
    odds: float  # quota presa
    won: bool

    @property
    def value(self) -> float:
        return self.probability * self.odds - 1.0


@dataclass(frozen=True)
class VersusGroup:
    n: int
    won: int
    expected_wins: float  # quante Archie se ne aspettava
    roi: float  # rendimento come singole a puntata fissa
    avg_value: float  # valore medio secondo Archie alla quota presa


@dataclass(frozen=True)
class Versus:
    judged: int  # selezioni chiuse con una probabilità di Archie
    without_archie: int  # selezioni chiuse senza fotografia o senza probabilità
    skill: float | None  # vinte − attese
    skill_std_error: float | None
    agreed: VersusGroup | None  # Archie vedeva valore (≥ 0)
    disagreed: VersusGroup | None  # Archie non l'avrebbe giocata


def group(picks: Sequence[JudgedPick]) -> VersusGroup | None:
    if not picks:
        return None
    profit = sum(p.odds - 1.0 if p.won else -1.0 for p in picks)
    return VersusGroup(
        n=len(picks),
        won=sum(p.won for p in picks),
        expected_wins=sum(p.probability for p in picks),
        roi=profit / len(picks),
        avg_value=sum(p.value for p in picks) / len(picks),
    )


def versus(picks: Sequence[JudgedPick], without_archie: int = 0) -> Versus:
    if not picks:
        return Versus(0, without_archie, None, None, None, None)
    skill = sum(p.won for p in picks) - sum(p.probability for p in picks)
    std = math.sqrt(sum(p.probability * (1 - p.probability) for p in picks))  # varianza di una somma di prove indipendenti
    return Versus(
        judged=len(picks),
        without_archie=without_archie,
        skill=skill,
        skill_std_error=std,
        agreed=group([p for p in picks if p.value >= 0]),
        disagreed=group([p for p in picks if p.value < 0]),
    )


def archie_probability(snapshot_match: dict[str, Any] | None, market: str, pick: str) -> float | None:
    """La probabilità di Archie per un esito, letta dalla fotografia della pagina partita salvata con la schedina."""
    prediction = (snapshot_match or {}).get("prediction") or {}
    reference = prediction.get("market") or {}  # mercato senza margine (Pinnacle, Betfair o media)
    model = prediction.get("markets") or {}
    if market in reference and pick in reference[market].get("probabilities", {}):
        return float(reference[market]["probabilities"][pick])
    if market == "DC" and "1X2" in reference:
        p = reference["1X2"]["probabilities"]
        return float(sum(p[o] for o in pick))  # "1X" = P(1) + P(X)
    if market in model and pick in model[market]:
        return float(model[market][pick])
    return None
