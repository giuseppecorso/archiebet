"""Previsioni di Archie per partita (sezione 14.2: calcolate una volta, lette da tutti gli utenti)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime


class MatchPrediction(Base):
    """L'ultima previsione PRIMA del calcio d'inizio: dopo la partita resta com'era (serve per giudicare Archie)."""

    __tablename__ = "match_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), unique=True)
    model_version: Mapped[str] = mapped_column(String(20))
    data_version: Mapped[str] = mapped_column(String(40))  # "partite finite:ultimo calcio d'inizio" usati
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    data_until: Mapped[datetime] = mapped_column(UTCDateTime)  # calcio d'inizio dell'ultimo risultato usato
    home_rating: Mapped[float] = mapped_column(Float)  # Elo al momento del calcolo
    away_rating: Mapped[float] = mapped_column(Float)
    expected_home_goals: Mapped[float] = mapped_column(Float)
    expected_away_goals: Mapped[float] = mapped_column(Float)
    markets: Mapped[dict[str, Any]] = mapped_column(JSON)  # mercato → esito → probabilità


class RadarSignal(Base):
    """Segnale del radar per partita ed esito (D57), la base della simulazione dal vivo (D59).

    La prima volta che il radar vede valore è la "giocata simulata": quota e valore restano quelli.
    I campi latest_* seguono le quote fino al calcio d'inizio; closing_* e clv arrivano con la chiusura.
    """

    __tablename__ = "radar_signals"
    __table_args__ = (UniqueConstraint("match_id", "market", "selection"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    market: Mapped[str] = mapped_column(String(20))
    selection: Mapped[str] = mapped_column(String(20))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    bookmaker: Mapped[str] = mapped_column(String(30))  # dove giocarla
    price: Mapped[float] = mapped_column(Float)
    fair_probability: Mapped[float] = mapped_column(Float)
    fair_source: Mapped[str] = mapped_column(String(30))
    value: Mapped[float] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime)  # ultimo controllo prima del calcio d'inizio
    latest_bookmaker: Mapped[str | None] = mapped_column(String(30))  # None = quota sparita
    latest_price: Mapped[float | None] = mapped_column(Float)
    latest_value: Mapped[float | None] = mapped_column(Float)
    closing_source: Mapped[str | None] = mapped_column(String(30))
    closing_fair_probability: Mapped[float | None] = mapped_column(Float)
    clv: Mapped[float | None] = mapped_column(Float)
    won: Mapped[bool | None] = mapped_column(Boolean)  # None = risultato non ancora noto
