"""Campionati e squadre: un'unica anagrafica, con i nomi usati da ciascuna fonte."""

import re
import unicodedata

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.models import Competition, Match, Team, TeamAlias

COMPETITIONS = {
    "ITA-A": {"name": "Serie A", "country": "Italia", "tier": 1},
    "ITA-B": {"name": "Serie B", "country": "Italia", "tier": 2},
    "ITA-C-A": {"name": "Serie C · Girone A", "country": "Italia", "tier": 3},
    "ITA-C-B": {"name": "Serie C · Girone B", "country": "Italia", "tier": 3},
    "ITA-C-C": {"name": "Serie C · Girone C", "country": "Italia", "tier": 3},
    "ENG-1": {"name": "Premier League", "country": "Inghilterra", "tier": 1},
    "ESP-1": {"name": "LaLiga", "country": "Spagna", "tier": 1},
    "GER-1": {"name": "Bundesliga", "country": "Germania", "tier": 1},
    "FRA-1": {"name": "Ligue 1", "country": "Francia", "tier": 1},
}

# Ordine dei paesi nei menu (specifiche, sezione 3)
COUNTRY_ORDER = ["Italia", "Inghilterra", "Spagna", "Germania", "Francia"]


def competition_sort_key(c: Competition) -> tuple[int, int, str]:
    """Prima il paese (Italia in testa), poi la categoria, poi il nome."""
    country = COUNTRY_ORDER.index(c.country) if c.country in COUNTRY_ORDER else len(COUNTRY_ORDER)
    return country, c.tier, c.name

# Sigle e parole che non distinguono una squadra dall'altra
_NOISE = {
    "ac", "acd", "acr", "as", "asd", "ss", "ssc", "ssd", "ssdarl", "us", "usd", "fc", "fbc", "sc", "cf", "srl",
    "calcio", "football", "club", "sporting", "1913", "polisportiva", "acf", "cfc", "bc",
}  # fmt: skip

# Nomi "ripuliti" che indicano la stessa squadra pur essendo scritti in modo diverso dalle fonti
_SAME_TEAM = {
    "feralpisalo": "feralpisalo",
    "feralpi salo": "feralpisalo",
    "sudtirol": "sudtirol",
    "alto adige": "sudtirol",
    "spal 2013": "spal",
    "hellas verona": "verona",
    "inter milan": "inter",
    "internazionale": "inter",
    "ac milan": "milan",
    "as roma": "roma",
    # OddsPapi aggiunge la città al nome
    "juventus turin": "juventus",
    "inter milano": "inter",
    "lazio rome": "lazio",
    "sampdoria genoa": "sampdoria",
    "sudtirol bolzano": "sudtirol",
    "l r vicenza": "vicenza",
    # OddsPapi usa i nomi completi, football-data le abbreviazioni (campionati esteri)
    "athletic bilbao": "ath bilbao",
    "atletico madrid": "ath madrid",
    "ca osasuna": "osasuna",
    "deportivo alaves": "alaves",
    "espanyol barcelona": "espanol",
    "levante ud": "levante",
    "rc celta de vigo": "celta",
    "rc deportivo de a coruna": "la coruna",
    "racing santander": "santander",
    "rayo vallecano": "vallecano",
    "real betis seville": "betis",
    "real sociedad san sebastian": "sociedad",
    "bayer leverkusen": "leverkusen",
    "borussia dortmund": "dortmund",
    "borussia monchengladbach": "m gladbach",
    "eintracht frankfurt": "ein frankfurt",
    "fsv mainz": "mainz",
    "hamburger sv": "hamburg",
    "paderborn 07": "paderborn",
    "sv 07 elversberg": "elversberg",
    "tsg hoffenheim": "hoffenheim",
    "vfb stuttgart": "stuttgart",
    "afc bournemouth": "bournemouth",
    "brighton hove albion": "brighton",
    "coventry city": "coventry",
    "hull city": "hull",
    "ipswich town": "ipswich",
    "leeds united": "leeds",
    "manchester city": "man city",
    "manchester united": "man united",
    "newcastle united": "newcastle",
    "nottingham forest": "nott m forest",
    "sunderland afc": "sunderland",
    "tottenham hotspur": "tottenham",
    "aj auxerre": "auxerre",
    "angers sco": "angers",
    "estac troyes": "troyes",
    "lille osc": "lille",
    "ogc nice": "nice",
    "olympique lyon": "lyon",
    "olympique marseille": "marseille",
    "paris saint germain": "paris sg",
    "racing de lens": "lens",
    "stade brest 29": "brest",
    "stade rennais": "rennes",
    "strasbourg alsace": "strasbourg",
    "1 cologne": "koln",
    # Stessa società dopo una rifondazione
    "vicenza virtus": "vicenza",
    "lr vicenza": "vicenza",
    "robur siena": "siena",
    "athletic carpi": "carpi",
}

# Nome da mostrare quando quello della fonte non è quello usato in Italia
DISPLAY_NAMES = {
    "Atalanta II": "Atalanta U23",
    "Milan II": "Milan Futuro",
    "SS Monopoli": "Monopoli",
    "Vicenza Virtus": "Vicenza",
    "Robur Siena": "Siena",
    "Athletic Carpi": "Carpi",
}


def normalize_team_name(name: str) -> str:
    """"SS Monopoli 1966" → "monopoli"; "FeralpiSalò" → "feralpisalo". Serve solo per confrontare."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    words = [w for w in text.split() if w not in _NOISE and not re.fullmatch(r"(18|19|20)\d\d", w)]
    joined = " ".join(words)
    return _SAME_TEAM.get(joined, joined)


def ensure_competitions(db: Session) -> dict[str, Competition]:
    found = {c.code: c for c in db.scalars(select(Competition))}
    for code, data in COMPETITIONS.items():
        if code not in found:
            found[code] = Competition(code=code, **data)
            db.add(found[code])
    db.flush()
    return found


class TeamResolver:
    """Trova la squadra dal codice o nome usato da una fonte; se non esiste ancora la crea.

    alias: identificativo stabile presso la fonte (nome per football-data, id numerico per API-Football)
    name: nome da mostrare se la squadra va creata (di solito coincide con l'alias)
    """

    def __init__(self, db: Session, source: str, country: str = "Italia"):
        self.db = db
        self.source = source
        self.country = country
        self._cache: dict[str, Team] = {}
        self._by_normalized: dict[str, Team] | None = None

    def _normalized_index(self) -> dict[str, Team]:
        if self._by_normalized is None:
            self._by_normalized = {}
            for team in self.db.scalars(select(Team).where(Team.country == self.country)):
                self._by_normalized.setdefault(normalize_team_name(team.name), team)
            for alias, team in self.db.execute(
                select(TeamAlias.alias, Team).join(Team, TeamAlias.team_id == Team.id).where(Team.country == self.country)
            ).all():
                self._by_normalized.setdefault(normalize_team_name(alias), team)
        return self._by_normalized

    def resolve(self, alias: str, name: str | None = None) -> Team:
        if alias in self._cache:
            return self._cache[alias]
        name = name or alias
        team = self.db.scalar(
            select(Team).join(TeamAlias, TeamAlias.team_id == Team.id).where(TeamAlias.source == self.source, TeamAlias.alias == alias)
        )
        if team is None:
            key = normalize_team_name(name)
            team = self._normalized_index().get(key)
            if team is None:
                team = Team(name=DISPLAY_NAMES.get(name, name), country=self.country)
                self.db.add(team)
                self.db.flush()
                self._normalized_index()[key] = team
            self.db.add(TeamAlias(team_id=team.id, source=self.source, alias=alias))
        self._cache[alias] = team
        return team


def merge_teams(db: Session, keep: Team, drop: Team) -> None:
    """Unisce due squadre che sono la stessa: partite e nomi delle fonti passano a `keep`, `drop` sparisce."""
    if keep.id == drop.id:
        return
    db.execute(update(Match).where(Match.home_team_id == drop.id).values(home_team_id=keep.id))
    db.execute(update(Match).where(Match.away_team_id == drop.id).values(away_team_id=keep.id))
    db.execute(update(TeamAlias).where(TeamAlias.team_id == drop.id).values(team_id=keep.id))
    db.delete(drop)
    db.flush()


def tidy_teams(db: Session, log=print) -> int:
    """Applica le regole di nomi e unioni alle squadre già nel database. Restituisce quante modifiche ha fatto."""
    changes = 0
    for team in db.scalars(select(Team)):
        if team.name in DISPLAY_NAMES and not db.scalar(select(Team).where(Team.name == DISPLAY_NAMES[team.name], Team.country == team.country)):
            log(f"Rinomino '{team.name}' in '{DISPLAY_NAMES[team.name]}'")
            team.name = DISPLAY_NAMES[team.name]
            changes += 1
    db.flush()

    groups: dict[tuple[str, str], list[Team]] = {}
    for team in db.scalars(select(Team).order_by(Team.id)):
        groups.setdefault((team.country, normalize_team_name(team.name)), []).append(team)
    for teams in groups.values():
        if len(teams) < 2:
            continue

        def played(t: Team) -> int:
            return db.scalar(select(func.count()).select_from(Match).where(or_(Match.home_team_id == t.id, Match.away_team_id == t.id)))

        keep = max(teams, key=played)  # resta il nome con più partite (di solito quello di football-data)
        for drop in teams:
            if drop is not keep:
                log(f"Unisco '{drop.name}' a '{keep.name}'")
                merge_teams(db, keep, drop)
                changes += 1
    db.commit()
    return changes
