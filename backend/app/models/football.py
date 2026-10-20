"""Dati PER PARTITA (sezione 14.2): campionati, squadre, partite, quote. Nessun user_id."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # es. "ITA-A", "ITA-C-A"
    name: Mapped[str] = mapped_column(String(80))  # es. "Serie A", "Serie C · Girone A"
    country: Mapped[str] = mapped_column(String(40))
    tier: Mapped[int] = mapped_column(Integer)  # 1 = massima serie


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("name", "country"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))  # nome mostrato nell'app
    country: Mapped[str] = mapped_column(String(40))
    # Stadio di casa (D76): città da API-Football, coordinate dal geocoding Open-Meteo; servono a meteo e distanze
    home_city: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    surface: Mapped[str | None] = mapped_column(String(30))  # "grass", "artificial turf", ...


class TeamAlias(Base):
    """Come ogni fonte chiama una squadra: "Verona" per una, "Hellas Verona" per un'altra."""

    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("source", "alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30))
    alias: Mapped[str] = mapped_column(String(80))


class MatchStatus:
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    POSTPONED = "postponed"  # rinviata, data da definire
    CANCELLED = "cancelled"  # annullata o sospesa senza risultato


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        # In campionato ogni coppia casa-trasferta si gioca una sola volta a stagione
        UniqueConstraint("competition_id", "season", "home_team_id", "away_team_id"),
        Index("ix_matches_kickoff_at", "kickoff_at"),
        Index("ix_matches_home_kickoff", "home_team_id", "kickoff_at"),
        Index("ix_matches_away_kickoff", "away_team_id", "kickoff_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    season: Mapped[str] = mapped_column(String(7))  # "2025/26"
    kickoff_at: Mapped[datetime] = mapped_column(UTCDateTime)
    kickoff_has_time: Mapped[bool] = mapped_column(Boolean, default=True)  # le stagioni vecchie hanno solo la data
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.SCHEDULED)
    matchday: Mapped[int | None] = mapped_column(Integer)  # giornata di campionato
    venue_name: Mapped[str | None] = mapped_column(String(120))
    venue_city: Mapped[str | None] = mapped_column(String(80))

    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    ht_home_goals: Mapped[int | None] = mapped_column(Integer)
    ht_away_goals: Mapped[int | None] = mapped_column(Integer)
    home_xg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    away_xg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    home_shots: Mapped[int | None] = mapped_column(Integer)
    away_shots: Mapped[int | None] = mapped_column(Integer)
    home_shots_on_target: Mapped[int | None] = mapped_column(Integer)
    away_shots_on_target: Mapped[int | None] = mapped_column(Integer)
    home_corners: Mapped[int | None] = mapped_column(Integer)
    away_corners: Mapped[int | None] = mapped_column(Integer)
    home_fouls: Mapped[int | None] = mapped_column(Integer)
    away_fouls: Mapped[int | None] = mapped_column(Integer)
    home_yellow: Mapped[int | None] = mapped_column(Integer)
    away_yellow: Mapped[int | None] = mapped_column(Integer)
    home_red: Mapped[int | None] = mapped_column(Integer)
    away_red: Mapped[int | None] = mapped_column(Integer)
    referee: Mapped[str | None] = mapped_column(String(80))

    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    competition: Mapped[Competition] = relationship(lazy="joined")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id], lazy="joined")
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id], lazy="joined")


class MatchSource(Base):
    """Codice della partita presso ogni fonte (es. id del fixture su API-Football): serve per formazioni e live."""

    __tablename__ = "match_sources"
    __table_args__ = (UniqueConstraint("source", "external_id"), UniqueConstraint("match_id", "source"))

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(40))


class MatchOdds(Base):
    """Una quota: partita × fonte × bookmaker × mercato × esito, di apertura o di chiusura.

    bookmaker: "pinnacle", "bet365", "betfair_ex", "market_max", "market_avg", ...
    market: "1X2" (esiti "1","X","2"), "OU2.5" (esiti "over","under").
    """

    __tablename__ = "match_odds"
    __table_args__ = (UniqueConstraint("match_id", "source", "bookmaker", "market", "selection", "is_closing"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30))
    bookmaker: Mapped[str] = mapped_column(String(30))
    market: Mapped[str] = mapped_column(String(20))
    selection: Mapped[str] = mapped_column(String(20))
    price: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    is_closing: Mapped[bool] = mapped_column(Boolean)
