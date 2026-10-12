"""Previsioni di Archie per partita (sezione 14.2: calcolate una volta, lette da tutti gli utenti)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
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
