"""Archie tifoso (D102): fatti delle squadre dalle notizie (Haiku) e giudizio sulla partita (Sonnet)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.ai.client import Ai

FACT_KINDS = (
    "assente",  # infortunato o indisponibile
    "rientro",  # torna disponibile
    "squalifica",
    "allenatore_nuovo",
    "allenatore_in_bilico",
    "societa_in_crisi",  # stipendi non pagati, proprietà in difficoltà, rischio esclusione
    "penalizzazione",
    "acquisto",
    "cessione",
    "clima_positivo",
    "clima_negativo",
)
FactKind = Literal[
    "assente", "rientro", "squalifica", "allenatore_nuovo", "allenatore_in_bilico", "societa_in_crisi",
    "penalizzazione", "acquisto", "cessione", "clima_positivo", "clima_negativo",
]  # fmt: skip


class Fact(BaseModel):
    item: int  # numero della notizia da cui viene
    team: str  # nome esatto dalla lista delle squadre
    kind: FactKind
    player: str | None
    detail: str  # una frase breve in italiano


class Extraction(BaseModel):
    facts: list[Fact]


class Judgment(BaseModel):
    side: Literal["home", "away", "none"]
    strength: Literal["lieve", "netta", "nessuna"]
    reason: str


EXTRACT_SYSTEM = """Sei l'assistente di un tifoso esperto di Serie C. Ricevi notizie numerate (data, titolo e a volte un riassunto).
Estrai SOLO fatti concreti che possono influire sulle prossime partite di campionato di una squadra della lista:
assente (infortunato/indisponibile), rientro, squalifica, allenatore_nuovo, allenatore_in_bilico, societa_in_crisi
(stipendi non pagati, proprietà in difficoltà, rischio esclusione), penalizzazione, acquisto, cessione,
clima_positivo, clima_negativo (spogliatoio, contestazioni, entusiasmo).

Regole:
- team deve essere ESATTAMENTE uno dei nomi della lista; se la notizia riguarda un'altra squadra, ignorala.
- Ignora altri sport (calcio a 5, basket, volley...), settori giovanili, calcio femminile, altre categorie,
  biglietti, cronache di partite già giocate senza conseguenze, opinioni generiche, voci di mercato non concluse.
- Non inventare: usa solo ciò che è scritto nella notizia. Una notizia può dare zero, uno o più fatti.
- player: il giocatore o l'allenatore coinvolto, se c'è; altrimenti null.
- detail: una frase breve in italiano (al massimo 20 parole), con i tempi se scritti (es. "fuori 3 settimane").
- item: il numero della notizia da cui viene il fatto.
- Un esonero è allenatore_nuovo anche se il sostituto non è ancora scelto; allenatore_in_bilico solo se è a rischio.

Squadre di Serie C:
{teams}"""

JUDGE_SYSTEM = """Sei Archie, un tifoso esperto di Serie C che segue ogni giorno le notizie di tutte le squadre.
Ti do i fatti recenti (con la data) delle due squadre di una partita. Non conosci le quote e non devi stimare numeri.

Domanda: rispetto alla loro situazione normale, le notizie indeboliscono una delle due squadre (o ne rafforzano una)
per QUESTA partita?
- side: la squadra favorita dalle notizie ("home" = casa, "away" = ospite), cioè quella a cui le notizie danno
  un vantaggio rispetto al solito; "none" se le notizie sono irrilevanti, equilibrate o troppo vaghe.
- strength: "netta" se il fatto è importante (più titolari fuori, allenatore appena cambiato, società nel caos),
  "lieve" se conta poco; "nessuna" quando side è "none".
- Pesa di più i titolari che le riserve e le notizie più recenti; un rientro annulla un'assenza dello stesso giocatore.
- reason: una o due frasi in italiano, semplici, che spiegano il giudizio."""


@dataclass(frozen=True)
class NewsText:
    published_at: datetime
    title: str
    summary: str


def extraction_prompt(items: Sequence[NewsText]) -> str:
    lines = []
    for n, it in enumerate(items, 1):
        text = f"{n}. [{it.published_at:%d/%m %H:%M}] {it.title}"
        if it.summary and it.summary not in it.title:
            text += f" — {it.summary}"
        lines.append(text)
    return "Notizie:\n" + "\n".join(lines)


def extract_facts(ai: Ai, model: str, teams: Sequence[str], items: Sequence[NewsText]) -> list[Fact]:
    system = EXTRACT_SYSTEM.format(teams="\n".join(sorted(teams)))
    return ai.parse("news-facts", model, system, extraction_prompt(items), Extraction).facts


@dataclass(frozen=True)
class FactText:
    published_at: datetime
    kind: str
    player: str | None
    detail: str


def judgment_prompt(home: str, away: str, kickoff: datetime, home_facts: Sequence[FactText], away_facts: Sequence[FactText]) -> str:
    def block(team: str, facts: Sequence[FactText]) -> str:
        if not facts:
            return f"{team}: nessuna notizia rilevante."
        latest: dict[tuple[str, str | None], FactText] = {}
        for f in sorted(facts, key=lambda x: x.published_at):  # lo stesso fatto da più notizie: vale il più recente
            latest[(f.kind, (f.player or "").lower() or None)] = f
        rows = [f"- [{f.published_at:%d/%m}] {f.kind}{f' ({f.player})' if f.player else ''}: {f.detail}" for f in latest.values()]
        return f"{team}:\n" + "\n".join(rows)

    return (f"Partita: {home} (casa) - {away} (ospite), {kickoff:%d/%m/%Y %H:%M}.\n\n"
            f"{block(home, home_facts)}\n\n{block(away, away_facts)}")  # fmt: skip


def judge_match(ai: Ai, model: str, home: str, away: str, kickoff: datetime,
                home_facts: Sequence[FactText], away_facts: Sequence[FactText]) -> Judgment:  # fmt: skip
    j = ai.parse("match-judgment", model, JUDGE_SYSTEM, judgment_prompt(home, away, kickoff, home_facts, away_facts), Judgment, effort="medium")
    if j.side == "none" or j.strength == "nessuna":  # coerenza: niente lato senza forza e viceversa
        return Judgment(side="none", strength="nessuna", reason=j.reason)
    return j
