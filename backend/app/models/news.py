"""Archie tifoso (D101-D102): notizie, fatti delle squadre, giudizi sulle partite, spesa dell'AI. Nessun user_id."""

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class NewsItem(Base):
    """Una notizia letta da un feed: solo titolo, riassunto e link (uso privato)."""

    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # "tuttoc" | "gnews"
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # quando l'AI l'ha letta


class TeamFact(Base):
    """Un fatto su una squadra estratto da una notizia (assente, squalifica, allenatore, ...)."""

    __tablename__ = "team_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    player: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)  # quella della notizia
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MatchInsight(Base):
    """Giudizio di Archie sulle notizie prima di una partita, con il consenso dei bookmaker di quel momento (D101)."""

    __tablename__ = "match_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    side: Mapped[str] = mapped_column(String(10))  # "home" | "away" | "none"
    strength: Mapped[str] = mapped_column(String(10))  # "lieve" | "netta" | ""
    reason: Mapped[str] = mapped_column(Text)
    facts: Mapped[int] = mapped_column(Integer)  # quanti fatti ha considerato
    p_home: Mapped[float | None] = mapped_column(Float)  # consenso 1X2 al momento del giudizio
    p_draw: Mapped[float | None] = mapped_column(Float)
    p_away: Mapped[float | None] = mapped_column(Float)
    close_home: Mapped[float | None] = mapped_column(Float)  # consenso 1X2 in chiusura
    close_draw: Mapped[float | None] = mapped_column(Float)
    close_away: Mapped[float | None] = mapped_column(Float)


class AiUsage(Base):
    """Una chiamata a Claude: token e costo, per il tetto di spesa mensile (D102)."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
