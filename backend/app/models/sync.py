"""Registro degli aggiornamenti dei dati: quando ogni fonte è stata aggiornata e se è andata bene."""

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), index=True)  # "football-data", "api-football", "predictions"
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    message: Mapped[str] = mapped_column(String(200))
