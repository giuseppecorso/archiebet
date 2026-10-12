"""Quote OddsPapi agganciate alle nostre partite: collegamento, quote attuali, chiusura, radar sui bookmaker italiani."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters.oddspapi import BOOKMAKERS, OPFixture
from app.forecast.radar_service import refresh_radar
from app.ingest.oddspapi import sync_oddspapi
from app.models import Match, MatchOdds, MatchSource, RadarSignal, TeamAlias
from tests.test_football_api import match_id, seeded  # noqa: F401 (fixture condivisa)

NAMES = {"1": "AC Milan", "2": "Inter Milano", "3": "Palermo FC", "4": "SSC Bari", "5": "Squadra Misteriosa"}


class FakeAdapter:
    """Stessa interfaccia di OddsPapiAdapter, senza rete."""

    def __init__(self, fixtures, current, history):
        self.fixtures, self.current, self._history = fixtures, current, history
        self.history_calls: list[tuple[str, tuple[str, ...]]] = []

    def upcoming(self, max_age):
        return self.fixtures, self.current

    def participants(self, max_age=None):
        return NAMES

    def history(self, fixture_id, slugs, max_age):
        self.history_calls.append((fixture_id, tuple(slugs)))
        wanted = {BOOKMAKERS[slug] for slug in slugs}
        return {bm: v for bm, v in self._history.get(fixture_id, {}).items() if bm in wanted}


def setup(db):
    milan_inter = db.get(Match, match_id(db, "Milan", "Inter"))
    kickoff = milan_inter.kickoff_at
    t0 = kickoff - timedelta(days=5)  # prima quota: già nel passato
    fixtures = [
        OPFixture("fx-mi", 23, kickoff + timedelta(hours=1), 1, 2, 0),  # orario un po' diverso: stessa partita
        OPFixture("fx-pb", 53, kickoff + timedelta(days=1), 3, 4, 0),  # Palermo-Bari: in Serie B
        OPFixture("fx-x", 23, kickoff, 5, 2, 0),  # squadra sconosciuta
    ]
    current = {"fx-mi": {"pinnacle": {"1X2": {"1": 3.0, "X": 3.5, "2": 2.4}}}}  # giuste: 0,3204 / 0,2747 / 0,4005
    history = {
        "fx-mi": {
            "sisal": {"1X2": {"1": [(t0, 3.4)], "X": [(t0, 3.3)], "2": [(t0, 2.3), (kickoff + timedelta(hours=5), 9.0)]}},
            "pinnacle": {"1X2": {"1": [(t0, 3.0), (kickoff - timedelta(minutes=5), 2.9)], "X": [(t0, 3.5)], "2": [(t0, 2.4)]}},
        }
    }
    return milan_inter, FakeAdapter(fixtures, current, history)


def odds(db, mid, closing):
    rows = db.scalars(select(MatchOdds).where(MatchOdds.match_id == mid, MatchOdds.source == "oddspapi", MatchOdds.is_closing.is_(closing)))
    return {(q.bookmaker, q.selection): float(q.price) for q in rows}


def test_links_matches_and_stores_current_odds(seeded, db):  # noqa: F811
    match, adapter = setup(db)
    now = datetime.now(UTC)
    logged = []
    report = sync_oddspapi(db, adapter, now, log=logged.append)
    assert report.linked == 2 and report.unknown_teams == ["Squadra Misteriosa"]
    assert db.scalar(select(MatchSource.match_id).where(MatchSource.external_id == "fx-mi")) == match.id
    assert db.scalar(select(TeamAlias.team_id).where(TeamAlias.source == "oddspapi", TeamAlias.alias == "1")) == match.home_team_id
    assert "Squadra Misteriosa" in logged[0]
    current = odds(db, match.id, closing=False)
    # Sisal dallo storico (prezzo valido adesso), Pinnacle dalla richiesta per campionato
    assert current[("sisal", "2")] == 2.3 and current[("pinnacle", "1")] == 3.0
    assert report.current == 1  # Palermo-Bari non ha quote
    assert adapter.history_calls[0][1][:3] == ("sisal.it", "snai.it", "eurobet.it")
    # Secondo giro: nessun collegamento nuovo, quote sostituite e non duplicate
    again = sync_oddspapi(db, adapter, now)
    assert again.linked == 0 and odds(db, match.id, closing=False) == current


def test_radar_uses_italian_bookmakers(seeded, db):  # noqa: F811
    match, adapter = setup(db)
    now = datetime.now(UTC)
    sync_oddspapi(db, adapter, now)
    refresh_radar(db, now)
    [s] = db.scalars(select(RadarSignal).where(RadarSignal.match_id == match.id))
    # Pinnacle 3,0 / 3,5 / 2,4 senza margine → 1 = 0,3218; Sisal paga il 1 a 3,4 → +9,4%
    fair_home = (1 / 3.0) / (1 / 3.0 + 1 / 3.5 + 1 / 2.4)
    assert (s.selection, s.bookmaker, s.price, s.fair_source) == ("1", "sisal", 3.4, "pinnacle")
    assert s.value == pytest.approx(fair_home * 3.4 - 1, abs=1e-5)


def test_closing_from_price_history(seeded, db):  # noqa: F811
    match, adapter = setup(db)
    now = datetime.now(UTC)
    sync_oddspapi(db, adapter, now)
    later = match.kickoff_at + timedelta(hours=3)
    report = sync_oddspapi(db, adapter, later)
    assert report.closing == 1
    # ultimo prezzo prima del calcio d'inizio (2,9 cinque minuti prima), solo Pinnacle
    assert odds(db, match.id, closing=True) == {("pinnacle", "1"): 2.9, ("pinnacle", "X"): 3.5, ("pinnacle", "2"): 2.4}
    assert adapter.history_calls[-1] == ("fx-mi", ("pinnacle",))
    assert sync_oddspapi(db, adapter, later).closing == 0  # già salvata
