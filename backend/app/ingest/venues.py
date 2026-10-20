"""Stadi di casa delle squadre (D76): città e campo da API-Football, coordinate da Open-Meteo."""

import html
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.api_football import SOURCE as AF_SOURCE
from app.adapters.api_football import ApiFootballAdapter
from app.adapters.open_meteo import OpenMeteoAdapter
from app.ingest.teams import normalize_team_name
from app.models import Team, TeamAlias

# Paese come lo scrive API-Football → (paese in ArchieBet, codice ISO per il geocoding)
COUNTRIES = {"Italy": ("Italia", "IT"), "England": ("Inghilterra", "GB"), "Spain": ("Spagna", "ES"),
             "Germany": ("Germania", "DE"), "France": ("Francia", "FR")}  # fmt: skip
# Campionati di API-Football con le nostre squadre: A, B, C (3 gironi), top 5 e seconde divisioni
# Città che il geocoding conosce con un altro nome
CITY_ALIASES = {"Reggio Emilia": "Reggio nell'Emilia", "Iruñea": "Pamplona", "Falmer": "Brighton", "Monaco": "Monaco|MC",
                "Andorra la Vella": "Andorra la Vella|AD", "La Coruña": "A Coruña", "Amorebieta-Echano": "Amorebieta"}  # fmt: skip


def city_candidates(city: str, iso: str) -> list[tuple[str, str]]:
    """Modi di cercare una città: nome ripulito ("Nottingham, Nottinghamshire" → "Nottingham"), alias, paese giusto."""
    clean = html.unescape(city).split(",")[0].split("(")[0].strip()
    out = []
    for name in (city.strip(), clean):
        alias = CITY_ALIASES.get(name, name)
        name, code = alias.split("|") if "|" in alias else (alias, iso)
        if (name, code) not in out:
            out.append((name, code))
    return out


LEAGUES = (135, 136, 138, 942, 943, 39, 40, 140, 141, 78, 79, 61, 62)
SEASONS = (2021, 2022, 2023, 2024, 2025)  # piano Pro: anche 2021 e 2025 (D89), per riconoscere le squadre di ogni stagione


@dataclass
class VenueReport:
    matched: int = 0
    located: int = 0
    unknown: list[str] = field(default_factory=list)  # squadre di API-Football che non riconosciamo
    not_found: list[str] = field(default_factory=list)  # città senza coordinate


def sync_venues(
    db: Session,
    af: ApiFootballAdapter,
    meteo: OpenMeteoAdapter,
    leagues: Iterable[int] = LEAGUES,
    seasons: Iterable[int] = SEASONS,
    log: Callable[[str], None] = print,
) -> VenueReport:
    report = VenueReport()
    aliases = {a.alias: a.team_id for a in db.scalars(select(TeamAlias).where(TeamAlias.source == AF_SOURCE))}
    by_name: dict[tuple[str, str], Team] = {}
    for team in db.scalars(select(Team)):
        by_name.setdefault((team.country, normalize_team_name(team.name)), team)
    for alias, team in db.execute(select(TeamAlias.alias, Team).join(Team, TeamAlias.team_id == Team.id)).all():
        by_name.setdefault((team.country, normalize_team_name(alias)), team)

    seen: set[int] = set()
    for league in leagues:
        for season in seasons:
            for v in reversed(af.teams(league, season, max_age=timedelta(days=30))):  # le stagioni più recenti vincono
                if v.team.id in seen or v.country not in COUNTRIES:
                    continue
                seen.add(v.team.id)
                country, iso = COUNTRIES[v.country]
                team = db.get(Team, aliases[str(v.team.id)]) if str(v.team.id) in aliases else by_name.get((country, normalize_team_name(v.team.name)))
                if team is None:
                    report.unknown.append(f"{v.team.name} ({country})")
                    continue
                report.matched += 1
                team.home_city = v.city or team.home_city
                team.surface = v.surface or team.surface
                if team.home_city and team.latitude is None:
                    place = next((p for name, code in city_candidates(team.home_city, iso) if (p := meteo.place(name, code))), None)
                    if place is None:
                        report.not_found.append(f"{team.name}: {team.home_city}")
                    else:
                        team.latitude, team.longitude = place.latitude, place.longitude
                        report.located += 1
            db.commit()
    log(f"Stadi: {report.matched} squadre abbinate, {report.located} localizzate")
    if report.unknown:
        log(f"Squadre non riconosciute: {sorted(set(report.unknown))}")
    if report.not_found:
        log(f"Città senza coordinate: {report.not_found}")
    return report
