"""Le "forme" della bacheca da confrontare nella macchina del tempo (D171). Si aggiunge una variante solo prima di aprirla."""

from collections.abc import Sequence
from dataclasses import replace

from app.forecast.daily import Kind
from app.forecast.daily_replay import Chooser
from app.forecast.daily_service import choose_study_legs

LEGS_BEFORE_D174 = {"giorno": (1, 30), "weekend": (4, 6), "settimana": (1, 30)}


def _long_legs(kind: Kind) -> Kind:
    """Quante partite prima di D174."""
    legs = LEGS_BEFORE_D174.get(kind.key)
    return replace(kind, min_legs=legs[0], max_legs=legs[1]) if legs else kind


def before_d172(kind: Kind, studies: Sequence[tuple[int, list[dict]]]) -> list[tuple[int, dict]]:
    """La bacheca prima di D172: nessuna quota minima e la settimana dal livello cauto."""
    kind = _long_legs(kind)
    return choose_study_legs(replace(kind, level="cauto") if kind.key == "settimana" else kind, studies, min_price=0.0, max_real_price=None)


def before_d174(kind: Kind, studies: Sequence[tuple[int, list[dict]]]) -> list[tuple[int, dict]]:
    """La bacheca di D172: quota minima 1,40, multiple ancora lunghe."""
    return choose_study_legs(_long_legs(kind), studies, max_real_price=None)


def before_d179(kind: Kind, studies: Sequence[tuple[int, list[dict]]]) -> list[tuple[int, dict]]:
    """La bacheca di D174: multiple corte, nessun tetto alla quota vera."""
    return choose_study_legs(kind, studies, max_real_price=None)


VARIANTS: dict[str, Chooser] = {
    "prima": before_d172,
    "d172": before_d174,
    "d174": before_d179,
    "d179": choose_study_legs,  # la bacheca di oggi
}
