"""Dati PER UTENTE (sezione 14.2): giocate, selezioni, fotografie e impostazioni. Sempre con user_id."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow
from app.models.football import Match


class BetKind:
    REAL = "real"  # giocata davvero da un bookmaker
    SIMULATED = "simulated"  # "Gioca simulata": portafoglio separato, nessun soldo vero


class Bet(Base):
    """Una schedina (singola o multipla)."""

    __tablename__ = "bets"
    __table_args__ = (Index("ix_bets_user_placed", "user_id", "placed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    stake: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_odds: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    bookmaker: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | won | lost | void
    payout: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # quanto è tornato (0 se persa)
    note: Mapped[str | None] = mapped_column(String(300))
    placed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    selections: Mapped[list["BetSelection"]] = relationship(
        back_populates="bet", cascade="all, delete-orphan", order_by="BetSelection.id", lazy="selectin"
    )


class BetSelection(Base):
    __tablename__ = "bet_selections"

    id: Mapped[int] = mapped_column(primary_key=True)
    bet_id: Mapped[int] = mapped_column(ForeignKey("bets.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    market: Mapped[str] = mapped_column(String(10))  # 1X2 | DC | OU2.5 | GG
    pick: Mapped[str] = mapped_column(String(10))
    odds: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    status: Mapped[str] = mapped_column(String(10), default="open")
    fair_closing_odds: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))  # quota giusta di chiusura, senza margine
    clv: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    bet: Mapped[Bet] = relationship(back_populates="selections")
    match: Mapped[Match] = relationship(lazy="joined")


class BetSnapshot(Base):
    """"Fotografia" al momento della giocata: quote e numeri che si vedevano allora, salvati così com'erano.

    Serve all'autopsia "sfortuna o errore?" (Fase 6) senza rischio di guardare dati arrivati dopo.
    """

    __tablename__ = "bet_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    bet_id: Mapped[int] = mapped_column(ForeignKey("bets.id", ondelete="CASCADE"), unique=True)
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    weekly_budget: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # solo avviso, mai blocco (D39)
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    favorite_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    bookmakers: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
