"""Partite giocate lette dal database nel formato che serve al modello."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.football import Competition, Match, MatchStatus


@dataclass(frozen=True)
class Game:
    match_id: int
    competition_id: int
    kickoff_at: datetime
    season: str
    tier: int  # 1 = Serie A, 2 = Serie B, 3 = Serie C
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int


def load_games(db: Session) -> list[Game]:
    """Tutte le partite finite con risultato, in ordine di calcio d'inizio (a parità, per id)."""
    rows = db.execute(
        select(Match, Competition.tier)
        .join(Competition, Match.competition_id == Competition.id)
        .where(Match.status == MatchStatus.FINISHED, Match.home_goals.is_not(None), Match.away_goals.is_not(None))
        .order_by(Match.kickoff_at, Match.id)
    ).all()
    return [
        Game(m.id, m.competition_id, m.kickoff_at, m.season, tier, m.home_team_id, m.away_team_id, m.home_goals, m.away_goals)
        for m, tier in rows
    ]
