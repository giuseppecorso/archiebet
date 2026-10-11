"""Campionati e squadre: un'unica anagrafica, con i nomi usati da ciascuna fonte."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Team, TeamAlias

# Campionati gestiti. I gironi di Serie C arriveranno con la loro fonte dati.
COMPETITIONS = {
    "ITA-A": {"name": "Serie A", "country": "Italia", "tier": 1},
    "ITA-B": {"name": "Serie B", "country": "Italia", "tier": 2},
}


def ensure_competitions(db: Session) -> dict[str, Competition]:
    found = {c.code: c for c in db.scalars(select(Competition))}
    for code, data in COMPETITIONS.items():
        if code not in found:
            found[code] = Competition(code=code, **data)
            db.add(found[code])
    db.flush()
    return found


class TeamResolver:
    """Trova la squadra dal nome usato da una fonte; se non esiste ancora la crea."""

    def __init__(self, db: Session, source: str, country: str = "Italia"):
        self.db = db
        self.source = source
        self.country = country
        self._cache: dict[str, Team] = {}

    def resolve(self, alias: str) -> Team:
        if alias in self._cache:
            return self._cache[alias]
        team = self.db.scalar(
            select(Team).join(TeamAlias, TeamAlias.team_id == Team.id).where(TeamAlias.source == self.source, TeamAlias.alias == alias)
        )
        if team is None:
            team = self.db.scalar(select(Team).where(Team.name == alias, Team.country == self.country))
            if team is None:
                team = Team(name=alias, country=self.country)
                self.db.add(team)
                self.db.flush()
            self.db.add(TeamAlias(team_id=team.id, source=self.source, alias=alias))
        self._cache[alias] = team
        return team
