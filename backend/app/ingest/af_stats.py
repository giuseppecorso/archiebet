"""Statistiche di squadra e dei giocatori da API-Football (tiri, angoli, falli, cartellini) per le partite finite.

Tutto finisce nella cache su file, per sempre (le partite finite non cambiano): modelli e prove leggono da lì.
Due richieste per partita; si riprende da dove si era fermato e si ferma da solo con la riserva del giorno.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta

from app.adapters.api_football import ApiFootballAdapter, ApiFootballError, QuotaExhausted

FOREVER = timedelta(days=36500)
STATS_LEAGUES = {135: "Serie A", 136: "Serie B"}  # con statistiche dei giocatori (verificato con /leagues)


@dataclass
class StatsReport:
    fixtures: int = 0
    done: int = 0
    failed: int = 0
    stopped: str | None = None


def download_match_stats(adapter: ApiFootballAdapter, leagues: Iterable[int], seasons: Iterable[int],
                         log: Callable[[str], None] = print) -> StatsReport:  # fmt: skip
    report = StatsReport()
    try:
        for season in seasons:
            for league in leagues:
                fixtures = [f for f in adapter.fixtures(league, season, timedelta(days=1)) if f.status == "finished"]
                report.fixtures += len(fixtures)
                for n, fx in enumerate(fixtures, 1):
                    try:
                        adapter.fixture_statistics(fx.id, FOREVER)
                        adapter.fixture_players(fx.id, FOREVER)
                        report.done += 1
                    except ApiFootballError as exc:
                        report.failed += 1
                        log(f"partita {fx.id}: {exc}")
                    if n % 100 == 0:
                        log(f"{STATS_LEAGUES.get(league, league)} {season}: {n}/{len(fixtures)}")
    except QuotaExhausted as exc:
        report.stopped = str(exc)
    return report
