"""Chiamate a Claude con tetto di spesa mensile (D102): prima di ogni chiamata si controlla quanto si è speso nel mese,
dopo si registrano token e costo nella tabella ai_usage."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AiUsage

# Listino Anthropic ($ per milione di token: entrata, uscita), da platform.claude.com, ottobre 2026
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

T = TypeVar("T", bound=BaseModel)


class AiError(Exception):
    """La risposta non è utilizzabile (rifiuto, risposta troncata o non valida)."""


class BudgetExceeded(AiError):
    """Raggiunto il tetto di spesa del mese: niente chiamate fino al mese prossimo."""


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def month_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def month_spent(db: Session, now: datetime) -> float:
    total = db.scalar(select(func.sum(AiUsage.cost_usd)).where(AiUsage.created_at >= month_start(now)))
    return float(total or 0.0)


class Ai:
    def __init__(self, db: Session, api_key: str, budget_usd: float, client: Any = None,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):  # fmt: skip
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._db, self._client, self._budget, self._now = db, client, budget_usd, now

    def parse(self, purpose: str, model: str, system: str, user: str, output: type[T], max_tokens: int = 8000, effort: str = "low") -> T:
        """Una richiesta con risposta strutturata (validata da pydantic). Solleva BudgetExceeded o AiError."""
        if model not in PRICES:
            raise AiError(f"Modello senza prezzo nel listino: {model}")
        spent = month_spent(self._db, self._now())
        if spent >= self._budget:
            raise BudgetExceeded(f"Spesi {spent:.2f} $ su {self._budget:.2f} $ questo mese")
        response = self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output,
            output_config={"effort": effort},
        )
        usage = response.usage
        tokens_in = usage.input_tokens + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        self._db.add(AiUsage(created_at=self._now(), purpose=purpose, model=model, input_tokens=tokens_in,
                             output_tokens=usage.output_tokens, cost_usd=cost_usd(model, tokens_in, usage.output_tokens)))  # fmt: skip
        self._db.commit()
        if response.stop_reason != "end_turn" or response.parsed_output is None:
            raise AiError(f"Risposta non utilizzabile ({response.stop_reason})")
        return response.parsed_output
