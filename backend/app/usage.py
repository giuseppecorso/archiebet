"""Registro dei consumi: chiamate alle fonti dati e costi AI (sezione 14.7)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import UsageEvent


def record_usage(
    db: Session,
    source: str,
    *,
    units: int = 1,
    cost_eur: Decimal = Decimal(0),
    user_id: int | None = None,
) -> None:
    db.add(UsageEvent(source=source, units=units, cost_eur=cost_eur, user_id=user_id))
    db.commit()


def spent_since(db: Session, source_prefix: str, since: datetime, user_id: int | None = None) -> Decimal:
    """Euro spesi dalle fonti che iniziano con source_prefix a partire da `since` (di un utente o di tutti)."""
    query = select(func.coalesce(func.sum(UsageEvent.cost_eur), 0)).where(
        UsageEvent.source.startswith(source_prefix),
        UsageEvent.created_at >= since,
    )
    if user_id is not None:
        query = query.where(UsageEvent.user_id == user_id)
    return Decimal(str(db.scalar(query)))
