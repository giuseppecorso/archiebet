"""Unico punto di accesso all'AI (sezione 14.3).

Qui vivranno: scelta del modello (Haiku/Sonnet), prompt caching, risposte salvate alle domande
frequenti, quota per utente e tetto di spesa globale. In Fase 0 c'è solo il controllo della spesa;
le chiamate vere arrivano in Fase 6. Ricorda: l'AI spiega, i numeri li calcola il codice.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import Settings
from app.usage import spent_since

AI_SOURCE_PREFIX = "ai:"


class BudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class BudgetStatus:
    spent_eur: Decimal
    limit_eur: Decimal
    warning: bool  # superata la soglia di avviso
    exceeded: bool  # raggiunto il tetto: niente più chiamate


def budget_status(spent: Decimal, limit: Decimal, warning_ratio: Decimal) -> BudgetStatus:
    return BudgetStatus(
        spent_eur=spent,
        limit_eur=limit,
        warning=spent >= limit * warning_ratio,
        exceeded=spent >= limit,
    )


def month_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class AIGateway:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def _status(self, limit: float, user_id: int | None, now: datetime | None) -> BudgetStatus:
        since = month_start(now or datetime.now(UTC))
        spent = spent_since(self.db, AI_SOURCE_PREFIX, since, user_id)
        return budget_status(spent, Decimal(str(limit)), Decimal(str(self.settings.ai_budget_warning_ratio)))

    def global_status(self, now: datetime | None = None) -> BudgetStatus:
        return self._status(self.settings.ai_monthly_budget_eur, None, now)

    def user_status(self, user_id: int, now: datetime | None = None) -> BudgetStatus:
        return self._status(self.settings.ai_user_monthly_quota_eur, user_id, now)

    def ensure_can_spend(self, user_id: int | None, now: datetime | None = None) -> None:
        if self.global_status(now).exceeded:
            raise BudgetExceeded("Tetto di spesa AI del mese raggiunto")
        if user_id is not None and self.user_status(user_id, now).exceeded:
            raise BudgetExceeded("Hai esaurito la tua quota AI di questo mese")

    def ask(self, *args, **kwargs):
        raise NotImplementedError("Le chiamate all'AI arrivano in Fase 6")
