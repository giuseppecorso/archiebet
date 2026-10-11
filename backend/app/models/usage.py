from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class UsageEvent(Base):
    """Registro dei consumi (sezione 14.7): ogni chiamata a una fonte dati o all'AI.

    source: es. "api-football", "oddspapi", "ai:haiku", "ai:sonnet".
    user_id è vuoto per i lavori comuni (calcoli per partita), pieno per le richieste di un utente.
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    units: Mapped[int] = mapped_column(Integer, default=1)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal(0))
