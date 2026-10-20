"""Download dello storico API-Football per D89: cosa chiede e come si ferma col budget del giorno."""

from datetime import UTC, datetime

from app.adapters.api_football import AFTeam, AFVenue, QuotaExhausted
from app.ingest.af_history import CUP_LEAGUES, SERIE_C_LEAGUES, download_history


class FakeAF:
    def __init__(self, quota_after=None):
        self.calls, self.quota_after = [], quota_after

    def _count(self, what):
        self.calls.append(what)
        if self.quota_after is not None and len(self.calls) > self.quota_after:
            raise QuotaExhausted("finite")

    def teams(self, league, season, max_age):
        self._count(("teams", league, season))
        return [AFVenue(AFTeam(league * 10, "X"), "Italy", None, None, None)]

    def fixtures(self, league, season, max_age):
        self._count(("fixtures", league, season))
        return []

    def coaches(self, team_id, max_age):
        self._count(("coachs", team_id))
        return []

    def lineups(self, fixture_id, max_age):
        self._count(("lineups", fixture_id))
        return []


def test_downloads_teams_cups_coaches_and_serie_c_fixtures():
    af = FakeAF()
    report = download_history(af, seasons=[2024], lineup_seasons=[2024], now=datetime(2026, 10, 20, tzinfo=UTC), log=lambda _: None)
    kinds = [c[0] for c in af.calls]
    assert kinds.count("teams") == 13 and kinds.count("coachs") == 13  # una squadra finta per campionato
    assert {c[1] for c in af.calls if c[0] == "fixtures"} == set(CUP_LEAGUES) | set(SERIE_C_LEAGUES)
    assert report.stopped is None


def test_stops_cleanly_when_the_daily_budget_ends():
    report = download_history(FakeAF(quota_after=3), seasons=[2024], lineup_seasons=[2024], log=lambda _: None)
    assert report.stopped == "finite"
