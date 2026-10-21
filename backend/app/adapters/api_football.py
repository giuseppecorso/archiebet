"""Fonte dati API-Football (v3.football.api-sports.io): calendario, risultati, stadi; Serie C.

Verificato sulle risposte reali (ottobre 2026):
- autenticazione con l'intestazione "x-apisports-key"; /status non consuma richieste
- piano Free: 100 richieste al giorno, 10 al minuto, solo stagioni 2022-2024
  (per altre stagioni la risposta è 200 con errors = {"plan": "..."})
- le date sono in UTC; le squadre hanno un id stabile ma il nome è quello ATTUALE
  (es. Monterosi Tuscia compare come "Guidonia Montecelio 1937" anche nel 2022/23)
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.adapters.base import DataSourceAdapter
from app.adapters.cache import FileCache

SOURCE = "api-football"
BASE_URL = "https://v3.football.api-sports.io"

# id del campionato su API-Football → codice in ArchieBet
LEAGUES = {
    135: "ITA-A",
    136: "ITA-B",
    138: "ITA-C-A",
    942: "ITA-C-B",
    943: "ITA-C-C",
    39: "ENG-1",
    40: "ENG-2",
    140: "ESP-1",
    141: "ESP-2",
    78: "GER-1",
    79: "GER-2",
    61: "FRA-1",
    62: "FRA-2",
    2: "EU-CL",
    3: "EU-EL",
    848: "EU-ECL",
}

# Stati API-Football → stato in ArchieBet. Gli stati "in corso" restano "scheduled" finché non c'è il live (Fase 5).
FINISHED = {"FT", "AET", "PEN", "AWD", "WO"}
POSTPONED = {"PST", "TBD"}
CANCELLED = {"CANC", "ABD"}
LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}  # partita in corso (D92)

MIN_SECONDS_BETWEEN_CALLS = 6.5  # limite di 10 richieste al minuto, con margine


class ApiFootballError(Exception):
    """Errore restituito dal servizio (piano, chiave, parametri). Non viene mai salvato in cache."""


class QuotaExhausted(ApiFootballError):
    """Richieste del giorno quasi finite: ci fermiamo per lasciare una riserva."""


@dataclass(frozen=True)
class AFTeam:
    id: int
    name: str


@dataclass(frozen=True)
class AFFixture:
    id: int
    league_id: int
    season: int
    kickoff_at: datetime
    status: str  # "scheduled" | "finished" | "postponed" | "cancelled"
    matchday: int | None
    venue_name: str | None
    venue_city: str | None
    referee: str | None
    home: AFTeam
    away: AFTeam
    home_goals: int | None
    away_goals: int | None
    ht_home_goals: int | None
    ht_away_goals: int | None
    status_short: str = ""  # codice di API-Football: "1H", "HT", "2H", "FT", ...
    elapsed: int | None = None  # minuto di gioco (solo dal vivo)
    live_home_goals: int | None = None  # punteggio di adesso (anche a partita in corso)
    live_away_goals: int | None = None

    @property
    def is_live(self) -> bool:
        return self.status_short in LIVE


@dataclass(frozen=True)
class AFVenue:
    """Squadra con il suo stadio di casa (da /teams)."""

    team: AFTeam
    country: str  # in inglese, come lo scrive API-Football ("Italy", "England", ...)
    venue_name: str | None
    city: str | None
    surface: str | None


def parse_teams(body: dict[str, Any]) -> list[AFVenue]:
    out = []
    for item in body.get("response", []):
        team, venue = item["team"], item.get("venue") or {}
        out.append(AFVenue(AFTeam(team["id"], team["name"]), team.get("country") or "", venue.get("name"), venue.get("city"), venue.get("surface")))
    return out


@dataclass(frozen=True)
class AFCoachSpell:
    """Un periodo di un allenatore su una panchina (da /coachs): fine None = ancora lì."""

    coach_id: int
    name: str
    team_id: int
    start: date | None
    end: date | None


def _day(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


def parse_coach_spells(body: dict[str, Any], team_id: int) -> list[AFCoachSpell]:
    """Tutti i periodi sulla panchina di team_id, di tutti gli allenatori della risposta."""
    out = []
    for coach in body.get("response", []):
        for spell in coach.get("career") or []:
            if (spell.get("team") or {}).get("id") == team_id:
                out.append(AFCoachSpell(coach["id"], coach.get("name") or "", team_id, _day(spell.get("start")), _day(spell.get("end"))))
    return sorted(out, key=lambda c: c.start or date.min)


@dataclass(frozen=True)
class AFLineup:
    """Formazione ufficiale di una squadra in una partita (da /fixtures/lineups)."""

    team_id: int
    coach_id: int | None
    starters: tuple[int, ...]  # id dei giocatori titolari


def parse_lineups(body: dict[str, Any]) -> list[AFLineup]:
    out = []
    for item in body.get("response", []):
        starters = tuple(p["player"]["id"] for p in item.get("startXI") or [] if (p.get("player") or {}).get("id"))
        out.append(AFLineup(item["team"]["id"], (item.get("coach") or {}).get("id"), starters))
    return out


def map_status(short: str) -> str:
    if short in FINISHED:
        return "finished"
    if short in POSTPONED:
        return "postponed"
    if short in CANCELLED:
        return "cancelled"
    return "scheduled"


def parse_matchday(round_name: str | None) -> int | None:
    """"Girone C - 12" o "Regular Season - 7" → 12 / 7. Altri turni (playoff) → None."""
    if not round_name or " - " not in round_name:
        return None
    last = round_name.rsplit(" - ", 1)[1].strip()
    return int(last) if last.isdigit() else None


def parse_fixtures(body: dict[str, Any]) -> list[AFFixture]:
    fixtures = []
    for item in body.get("response", []):
        fx, league, teams = item["fixture"], item["league"], item["teams"]
        status = map_status(fx["status"]["short"])
        finished = status == "finished"
        halftime = (item.get("score") or {}).get("halftime") or {}
        fixtures.append(
            AFFixture(
                id=fx["id"],
                league_id=league["id"],
                season=league["season"],
                kickoff_at=datetime.fromisoformat(fx["date"]),
                status=status,
                matchday=parse_matchday(league.get("round")),
                venue_name=(fx.get("venue") or {}).get("name"),
                venue_city=(fx.get("venue") or {}).get("city"),
                referee=fx.get("referee"),
                home=AFTeam(teams["home"]["id"], teams["home"]["name"]),
                away=AFTeam(teams["away"]["id"], teams["away"]["name"]),
                home_goals=item["goals"]["home"] if finished else None,
                away_goals=item["goals"]["away"] if finished else None,
                ht_home_goals=halftime.get("home") if finished else None,
                ht_away_goals=halftime.get("away") if finished else None,
                status_short=fx["status"]["short"],
                elapsed=fx["status"].get("elapsed"),
                live_home_goals=item["goals"]["home"],
                live_away_goals=item["goals"]["away"],
            )
        )
    return fixtures


class ApiFootballAdapter(DataSourceAdapter):
    source = SOURCE

    def __init__(
        self,
        cache: FileCache,
        api_key: str,
        on_call: Callable[[str], None] | None = None,
        http_get: Callable[..., Any] | None = None,
        daily_reserve: int = 10,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        super().__init__(cache, on_call)
        self._api_key = api_key
        self._http_get = http_get or _http_get
        self._daily_reserve = daily_reserve
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None
        self._min_interval = MIN_SECONDS_BETWEEN_CALLS  # si adegua al piano con l'intestazione x-ratelimit-limit
        self.remaining_today: int | None = None

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.remaining_today is not None and self.remaining_today <= self._daily_reserve:
            raise QuotaExhausted(f"Restano {self.remaining_today} richieste oggi: tengo la riserva di {self._daily_reserve}")
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()
        status, headers, body = self._http_get(f"{BASE_URL}{path}", params, {"x-apisports-key": self._api_key})
        remaining = headers.get("x-ratelimit-requests-remaining")
        if remaining is not None and str(remaining).isdigit():
            self.remaining_today = int(remaining)
        per_minute = headers.get("x-ratelimit-limit")
        if per_minute is not None and str(per_minute).isdigit() and int(per_minute) > 0:
            self._min_interval = 60 / int(per_minute) * 1.25  # 25% di margine (Pro: 300 al minuto -> 0,25 s)
        if status != 200:
            raise ApiFootballError(f"HTTP {status} da {path}")
        if body.get("errors"):
            raise ApiFootballError(f"{path} {params}: {body['errors']}")
        return body

    def fixtures(self, league_id: int, season: int, max_age: timedelta) -> list[AFFixture]:
        params = {"league": league_id, "season": season}
        key = f"fixtures?league={league_id}&season={season}"
        return parse_fixtures(self.cached(key, max_age, lambda: self._request("/fixtures", params)))


    def live(self, league_ids: Sequence[int]) -> list[AFFixture]:
        """Partite in corso adesso nei campionati indicati (una richiesta, mai in cache)."""
        return parse_fixtures(self._request("/fixtures", {"live": "-".join(str(i) for i in league_ids)}))

    def fixtures_by_ids(self, fixture_ids: Sequence[int]) -> list[AFFixture]:
        """Situazione aggiornata di alcune partite (al massimo 20 per richiesta), mai in cache."""
        return parse_fixtures(self._request("/fixtures", {"ids": "-".join(str(i) for i in fixture_ids)}))

    def coaches(self, team_id: int, max_age: timedelta) -> list[AFCoachSpell]:
        """Allenatori della squadra con le date di ogni periodo in panchina."""
        body = self.cached(f"coachs?team={team_id}", max_age, lambda: self._request("/coachs", {"team": team_id}))
        return parse_coach_spells(body, team_id)

    def lineups(self, fixture_id: int, max_age: timedelta) -> list[AFLineup]:
        """Formazioni ufficiali di una partita (vuoto se non ancora uscite o non disponibili)."""
        body = self.cached(f"fixtures/lineups?fixture={fixture_id}", max_age, lambda: self._request("/fixtures/lineups", {"fixture": fixture_id}))
        return parse_lineups(body)

    def fixture_statistics(self, fixture_id: int, max_age: timedelta) -> dict[str, Any]:
        """Statistiche di squadra di una partita (tiri, angoli, falli, cartellini, possesso...): risposta grezza."""
        return self.cached(f"fixtures/statistics?fixture={fixture_id}", max_age, lambda: self._request("/fixtures/statistics", {"fixture": fixture_id}))

    def fixture_players(self, fixture_id: int, max_age: timedelta) -> dict[str, Any]:
        """Statistiche di ogni giocatore in una partita (minuti, tiri, falli, cartellini...): risposta grezza."""
        return self.cached(f"fixtures/players?fixture={fixture_id}", max_age, lambda: self._request("/fixtures/players", {"fixture": fixture_id}))

    def teams(self, league_id: int, season: int, max_age: timedelta) -> list[AFVenue]:
        """Squadre di un campionato con lo stadio di casa (città e tipo di campo)."""
        params = {"league": league_id, "season": season}
        return parse_teams(self.cached(f"teams?league={league_id}&season={season}", max_age, lambda: self._request("/teams", params)))


def _http_get(url: str, params: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, str], dict[str, Any]]:
    import httpx2

    response = httpx2.get(url, params=params, headers=headers, timeout=30)
    return response.status_code, {k.lower(): v for k, v in response.headers.items()}, response.json()
