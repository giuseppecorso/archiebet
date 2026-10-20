"""Storico da API-Football per le prove dei fattori D89: coppe, allenatori, formazioni (piano Pro).

Tutto finisce nella cache su file (le stagioni concluse per sempre): le prove leggono da lì, senza rete.
Richieste stimate: ~65 elenchi squadre, ~50 calendari di coppa, ~400 allenatori, ~4.600 formazioni di Serie C.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.adapters.api_football import ApiFootballAdapter, ApiFootballError, QuotaExhausted
from app.adapters.football_data import season_of
from app.ingest.venues import LEAGUES as LEAGUE_IDS

# Coppe che tolgono riposo: europee e nazionali dei nostri paesi (id verificati con /leagues il 2026-10-20)
CUP_LEAGUES = {
    2: "Champions League", 3: "Europa League", 848: "Conference League",
    137: "Coppa Italia", 891: "Coppa Italia Serie C", 45: "FA Cup", 48: "League Cup",
    143: "Copa del Rey", 81: "DFB-Pokal", 66: "Coupe de France",
}  # fmt: skip
SERIE_C_LEAGUES = (138, 942, 943)
FOREVER = timedelta(days=36500)


@dataclass
class HistoryReport:
    teams: int = 0
    cup_fixtures: int = 0
    coaches: int = 0
    lineups: int = 0
    stopped: str | None = None


def download_history(
    adapter: ApiFootballAdapter,
    seasons: Iterable[int],
    lineup_seasons: Iterable[int],
    now: datetime | None = None,
    log: Callable[[str], None] = print,
) -> HistoryReport:
    """Scarica (o legge dalla cache) quello che serve alle prove D89. Riprendibile: si ferma col budget del giorno."""
    current = season_of((now or datetime.now(UTC)).date())
    report = HistoryReport()
    seasons, lineup_seasons = list(seasons), list(lineup_seasons)

    def age(season: int) -> timedelta:
        return FOREVER if season < current else timedelta(days=1)

    try:
        team_ids: set[int] = set()
        for season in seasons:
            for league in LEAGUE_IDS:
                venues = _safe(lambda: adapter.teams(league, season, age(season)), [], log, f"squadre {league}/{season}")
                team_ids |= {v.team.id for v in venues}
                report.teams += len(venues)
            for league, name in CUP_LEAGUES.items():
                fixtures = _safe(lambda: adapter.fixtures(league, season, age(season)), [], log, f"{name} {season}")
                report.cup_fixtures += len(fixtures)
        log(f"Squadre: {len(team_ids)} diverse; partite di coppa: {report.cup_fixtures}")

        for team_id in sorted(team_ids):
            report.coaches += len(_safe(lambda: adapter.coaches(team_id, timedelta(days=30)), [], log, f"allenatori {team_id}"))
        log(f"Periodi di allenatori: {report.coaches}")

        for season in lineup_seasons:
            for league in SERIE_C_LEAGUES:
                for fx in adapter.fixtures(league, season, age(season)):
                    if fx.status != "finished":
                        continue
                    lineups = _safe(lambda: adapter.lineups(fx.id, FOREVER), [], log, f"formazioni {fx.id}")
                    report.lineups += bool(lineups)
            log(f"Formazioni Serie C fino al {season}: {report.lineups} partite")
    except QuotaExhausted as error:
        report.stopped = str(error)
        log(f"Mi fermo: {error}. Rilancia domani: riparte da dove è arrivato.")
    return report


def _safe(fetch, default, log, label):
    try:
        return fetch()
    except QuotaExhausted:
        raise
    except ApiFootballError as error:
        log(f"{label}: saltato ({error})")
        return default
