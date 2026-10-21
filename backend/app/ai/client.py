"""Chiamate a Claude dentro il tetto di spesa del gateway (sezione 14.3, D102-D103).

Prima di ogni chiamata il gateway controlla il tetto del mese; dopo, il costo finisce nel registro dei consumi
(usage_events, fonte "ai:<compito>:<modello>").
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.config import Settings
from app.usage import record_usage

# Listino Anthropic ($ per milione di token: entrata, uscita), da platform.claude.com, ottobre 2026
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
EUR_PER_USD = Decimal(1)  # prudente: 1 $ contato come 1 € (il dollaro vale meno), il tetto scatta prima

T = TypeVar("T", bound=BaseModel)


class AiError(Exception):
    """La risposta non è utilizzabile (rifiuto, risposta troncata o non valida)."""


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class Ai:
    def __init__(self, db: Session, api_key: str, settings: Settings, client: Any = None,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):  # fmt: skip
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._db, self._client, self._now = db, client, now
        self._gateway = AIGateway(db, settings)

    def parse(self, purpose: str, model: str, system: str, user: str, output: type[T], max_tokens: int = 8000, effort: str = "low",
              user_id: int | None = None) -> T:  # fmt: skip
        """Una richiesta con risposta strutturata (validata da pydantic). Solleva BudgetExceeded (gateway) o AiError."""
        if model not in PRICES:
            raise AiError(f"Modello senza prezzo nel listino: {model}")
        self._gateway.ensure_can_spend(user_id, self._now())
        response = self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output,
            output_config={"effort": effort},
        )
        self._record(purpose, model, response.usage, user_id)
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise AiError(f"Risposta non utilizzabile ({response.stop_reason})")
        return response.parsed_output

    def create(self, purpose: str, model: str, system: str, messages: list, tools: list | None = None, max_tokens: int = 8000,
               effort: str = "medium", user_id: int | None = None) -> Any:  # fmt: skip
        """Una richiesta libera (es. con strumenti): stesso tetto di spesa e stesso registro di parse()."""
        if model not in PRICES:
            raise AiError(f"Modello senza prezzo nel listino: {model}")
        self._gateway.ensure_can_spend(user_id, self._now())
        kwargs = {"tools": tools} if tools else {}
        response = self._client.messages.create(model=model, max_tokens=max_tokens, system=system, messages=messages,
                                                output_config={"effort": effort}, **kwargs)  # fmt: skip
        self._record(purpose, model, response.usage, user_id)
        if response.stop_reason in ("refusal", "max_tokens"):
            raise AiError(f"Risposta non utilizzabile ({response.stop_reason})")
        return response

    def _record(self, purpose: str, model: str, usage: Any, user_id: int | None) -> None:
        # La cache costa meno, ma si conta a prezzo pieno: per il tetto meglio sovrastimare
        tokens_in = usage.input_tokens + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        cost = Decimal(str(cost_usd(model, tokens_in, usage.output_tokens))) * EUR_PER_USD
        record_usage(self._db, f"ai:{purpose}:{model.removeprefix('claude-')}", units=tokens_in + usage.output_tokens, cost_eur=cost, user_id=user_id,
                     created_at=self._now())  # fmt: skip
