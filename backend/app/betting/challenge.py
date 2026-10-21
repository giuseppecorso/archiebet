"""Sfida contro Archie (Fase 6, D116): punti e crediti finti, solo per misurare il fiuto.

Ogni pronostico vale 10 crediti finti giocati alla quota giusta (senza margine): chi sceglie a caso o segue il mercato
in media resta a zero; i crediti salgono solo se si scelgono gli esiti che il mercato sottovaluta. Niente premi per
quanto si gioca (principio 7): ogni partita vale uguale.
"""

from collections.abc import Sequence
from dataclasses import dataclass

STAKE = 10.0


@dataclass(frozen=True)
class Settled:
    selection: str
    fair_odds: float
    outcome: str  # "1" | "X" | "2"


@dataclass(frozen=True)
class Score:
    picks: int
    correct: int
    credits: float

    @property
    def hit_rate(self) -> float | None:
        return self.correct / self.picks if self.picks else None


def outcome(home_goals: int, away_goals: int) -> str:
    return "1" if home_goals > away_goals else "X" if home_goals == away_goals else "2"


def credits(s: Settled) -> float:
    return STAKE * (s.fair_odds - 1) if s.selection == s.outcome else -STAKE


def score(settled: Sequence[Settled]) -> Score:
    return Score(len(settled), sum(s.selection == s.outcome for s in settled), round(sum(credits(s) for s in settled), 2))


def archie_pick(probs: dict[str, float]) -> str:
    """Archie sceglie l'esito più probabile secondo la stima migliore."""
    return max(("1", "X", "2"), key=lambda k: probs[k])
