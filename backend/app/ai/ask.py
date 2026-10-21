"""Chiedi ad Archie (Fase 6): risponde alle domande usando strumenti che leggono i dati dell'app.

Gli strumenti li fornisce chi chiama (l'API): restituiscono testo con numeri calcolati dal codice. L'AI sceglie quali
usare, poi risponde in italiano semplice citando solo quei numeri (principio 4).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai.client import Ai, AiError

MAX_STEPS = 6  # giri al massimo tra domanda, strumenti e risposta


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: dict[str, str]  # nome → descrizione (tutti stringhe o interi, tutti obbligatori)
    run: Callable[..., str]
    int_params: tuple[str, ...] = ()

    def schema(self) -> dict[str, Any]:
        props = {k: {"type": "integer" if k in self.int_params else "string", "description": v} for k, v in self.params.items()}
        return {"name": self.name, "description": self.description, "strict": True,
                "input_schema": {"type": "object", "properties": props, "required": list(self.params), "additionalProperties": False}}  # fmt: skip


ASK_SYSTEM = """Sei Archie, l'assistente di ArchieBet: un tifoso esperto e un analista onesto. Rispondi in italiano semplice, come a un amico.

Regole:
- Per i dati usa SEMPRE gli strumenti: partite, probabilità, quote, statistiche, notizie e giocate dell'utente. Non inventare
  numeri, giocatori o risultati; se gli strumenti non hanno il dato, dillo.
- Le probabilità e le quote giuste le calcola l'app: citale, non crearne di nuove.
- "Valore" c'è solo quando la quota del bookmaker supera la quota giusta con la regola dell'app (lo dicono le etichette).
  Non promettere vincite, non spingere a giocare di più; se una giocata non ha valore, dillo chiaramente.
- Uso privato, gioco responsabile: se l'utente sembra rincorrere le perdite, ricordagli i suoi limiti.
- Risposte brevi: 3-8 frasi o un elenco corto. Niente tabelle lunghe.
{context}"""


def ask(ai: Ai, model: str, question: str, tools: list[Tool], context: str = "", user_id: int | None = None,
        history: list[tuple[str, str]] | None = None) -> str:  # fmt: skip
    """Risposta di Archie; usa gli strumenti finché serve (al massimo MAX_STEPS giri)."""
    by_name = {t.name: t for t in tools}
    messages: list[dict[str, Any]] = []
    for q, a in history or []:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": question})
    system = ASK_SYSTEM.format(context=f"\nContesto: {context}" if context else "")
    for _ in range(MAX_STEPS):
        response = ai.create("ask", model, system, messages, tools=[t.schema() for t in tools], user_id=user_id)
        calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            if not text:
                raise AiError("Risposta vuota")
            return text
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for call in calls:
            tool = by_name.get(call.name)
            try:
                output = tool.run(**call.input) if tool else f"Strumento sconosciuto: {call.name}"
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": output[:12000] or "(nessun dato)"})
            except Exception as exc:  # noqa: BLE001 - l'errore torna all'AI come risultato, che può riprovare
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": f"Errore: {exc}", "is_error": True})
        messages.append({"role": "user", "content": results})
    raise AiError("Troppi passaggi: domanda troppo complessa, prova a dividerla")
