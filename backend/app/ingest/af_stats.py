"""Statistiche di squadra e dei giocatori da API-Football (tiri, angoli, falli, cartellini) per le partite finite.

Tutto finisce nella cache su file, per sempre (le partite finite non cambiano): modelli e prove leggono da lì.
Due richieste per partita; si riprende da dove si era fermato e si ferma da solo con la riserva del giorno.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta

import httpx2

from app.adapters.api_football import AFFixture, ApiFootballAdapter, ApiFootballError, QuotaExhausted, parse_fixtures
from app.adapters.cache import MISSING, FileCache
from app.forecast.player_props import PlayerGame, parse_players

FOREVER = timedelta(days=36500)
STATS_LEAGUES = {135: "Serie A", 136: "Serie B"}  # con statistiche dei giocatori (verificato con /leagues)


@dataclass
class StatsReport:
    fixtures: int = 0
    done: int = 0
    failed: int = 0
    stopped: str | None = None


def download_match_stats(adapter: ApiFootballAdapter, leagues: Iterable[int], seasons: Iterable[int],
                         log: Callable[[str], None] = print, players_only: bool = False) -> StatsReport:  # fmt: skip
    report = StatsReport()
    try:
        for season in seasons:
            for league in leagues:
                fixtures = [f for f in adapter.fixtures(league, season, timedelta(days=1)) if f.status == "finished"]
                report.fixtures += len(fixtures)
                for n, fx in enumerate(fixtures, 1):
                    try:
                        if not players_only:
                            adapter.fixture_statistics(fx.id, FOREVER)
                        adapter.fixture_players(fx.id, FOREVER)
                        report.done += 1
                    except QuotaExhausted:
                        raise  # è anche un ApiFootballError: qui ci si ferma, non si salta la partita
                    except ApiFootballError as exc:
                        report.failed += 1
                        log(f"partita {fx.id}: {exc}")
                    except httpx2.TransportError as exc:  # rete instabile (timeout, connessione caduta): si salta, al prossimo giro si riprende
                        report.failed += 1
                        log(f"partita {fx.id}: rete {exc}")
                    if n % 100 == 0:
                        log(f"{STATS_LEAGUES.get(league, league)} {season}: {n}/{len(fixtures)}")
    except QuotaExhausted as exc:
        report.stopped = str(exc)
    return report


# --- Lettura dalla cache per la pagina partita (D111) ----------------------------------------------------------------

_MEMO: dict[tuple[int, int], tuple[float, list]] = {}
MEMO_SECONDS = 1800  # i dati dei giocatori si rileggono dai file al massimo ogni 30 minuti


def season_fixtures(cache: FileCache, league: int, season: int) -> list[AFFixture]:
    body = cache.get(f"fixtures?league={league}&season={season}", FOREVER)
    return [] if body is MISSING else parse_fixtures(body)


def load_player_games(cache: FileCache, league: int, season: int) -> list[PlayerGame]:
    """Righe dei giocatori di un campionato e stagione, solo dalla cache (niente rete)."""
    key = (league, season)
    hit = _MEMO.get(key)
    if hit and time.monotonic() - hit[0] < MEMO_SECONDS:
        return hit[1]
    games = []
    for fx in season_fixtures(cache, league, season):
        if fx.status != "finished":
            continue
        body = cache.get(f"fixtures/players?fixture={fx.id}", FOREVER)
        if body is not MISSING:
            games += parse_players(body, fx.id, league, season, fx.kickoff_at, fx.home.id)
    _MEMO[key] = (time.monotonic(), games)
    return games
