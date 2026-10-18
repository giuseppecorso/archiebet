"""Quote OddsPapi agganciate alle nostre partite: collegamento, quote attuali, chiusura, radar sui bookmaker italiani."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.adapters.football_data import parse_csv
from app.adapters.oddspapi import BOOKMAKERS, OPFixture
from app.forecast.demargin import shin
from app.forecast.radar_service import refresh_radar
from app.ingest.football_data import import_matches
from app.ingest.oddspapi import sync_oddspapi
from app.models import Match, MatchOdds, MatchSource, RadarSignal, TeamAlias
from tests.test_football_api import day, match_id, seeded  # noqa: F401 (fixture condivisa)

NAMES = {"1": "AC Milan", "2": "Inter Milano", "3": "Palermo FC", "4": "SSC Bari", "5": "Squadra Misteriosa", "6": "AS Roma"}


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
    # elenco del giorno (più vecchio): Pinnacle 1X2 a 2,95 e Under/Over che lo storico non ha
    current = {"fx-mi": {"pinnacle": {"1X2": {"1": 2.95, "X": 3.5, "2": 2.45}, "OU2.5": {"over": 1.9, "under": 1.95}}}}
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
    assert current[("sisal", "2")] == 2.3
    assert current[("pinnacle", "1")] == 3.0  # lo storico (fresco) vince sull'elenco del giorno
    assert current[("pinnacle", "over")] == 1.9  # ma l'elenco riempie i mercati che mancano
    assert report.current == 1  # Palermo-Bari non ha quote
    assert adapter.history_calls[0][1] == ("pinnacle", "sisal.it", "eurobet.it")  # una sola chiamata per partita
    # Secondo giro: nessun collegamento nuovo, quote sostituite e non duplicate
    again = sync_oddspapi(db, adapter, now)
    assert again.linked == 0 and odds(db, match.id, closing=False) == current


def test_radar_uses_italian_bookmakers(seeded, db):  # noqa: F811
    match, adapter = setup(db)
    now = datetime.now(UTC)
    sync_oddspapi(db, adapter, now)
    refresh_radar(db, now)
    [s] = db.scalars(select(RadarSignal).where(RadarSignal.match_id == match.id))
    # Pinnacle 3,0 / 3,5 / 2,4 senza margine (Shin) → 1 ≈ 0,321; Sisal paga il 1 a 3,4 → +9,3% (soglia a 3,4: 3,1%)
    fair_home = shin([3.0, 3.5, 2.4])[0]
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


def test_creates_missing_matches_and_football_data_reuses_them(seeded, db):  # noqa: F811
    now = datetime.now(UTC)
    kickoff = (now + timedelta(days=9)).replace(hour=16, minute=0, second=0, microsecond=0)
    adapter = FakeAdapter([OPFixture("fx-new", 23, kickoff, 6, 1, 0)], {}, {})  # Roma-Milan, non ancora in calendario
    before = db.scalar(select(func.count()).select_from(Match))
    report = sync_oddspapi(db, adapter, now)
    assert report.created == 1
    new = db.scalar(select(Match).join(MatchSource).where(MatchSource.external_id == "fx-new"))
    assert (new.home_team.name, new.away_team.name, new.status, new.season) == ("Roma", "Milan", "scheduled", "2026/27")
    assert new.kickoff_at == kickoff

    # Anticipo: OddsPapi sposta l'orario di un'ora
    adapter.fixtures = [OPFixture("fx-new", 23, kickoff - timedelta(hours=1), 6, 1, 0)]
    assert sync_oddspapi(db, adapter, now).created == 0
    assert db.get(Match, new.id).kickoff_at == kickoff - timedelta(hours=1)

    # Arriva il calendario di football-data: stessa partita, nessun doppione
    import_matches(db, parse_csv(f"Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\nI1,{day(9)},15:00,Roma,Milan,1.9,3.4,4.0\n"))
    assert db.scalar(select(func.count()).select_from(Match)) == before + 1

    # Rinvio: Milan-Inter è in calendario tra 3 giorni, OddsPapi la dà tra 10 → stessa partita, niente doppioni
    milan_inter = match_id(db, "Milan", "Inter")
    adapter.fixtures = [OPFixture("fx-moved", 23, now + timedelta(days=10), 1, 2, 0)]
    report = sync_oddspapi(db, adapter, now)
    assert (report.created, report.linked) == (0, 1)
    assert db.scalar(select(MatchSource.match_id).where(MatchSource.external_id == "fx-moved")) == milan_inter

    # Partita già iniziata e mai vista: non si inventa
    adapter.fixtures = [OPFixture("fx-old", 53, now - timedelta(hours=2), 4, 3, 0)]  # Bari-Palermo
    assert sync_oddspapi(db, adapter, now).not_in_calendar == 1
