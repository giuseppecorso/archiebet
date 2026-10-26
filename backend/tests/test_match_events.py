"""Diretta (D133): cronaca con marcatori, cartellini e cambi da API-Football."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.adapters.api_football import event_kind, parse_events, parse_fixtures
from app.ingest.live import sync_live, sync_missing_events
from app.models import Match, MatchEvent, MatchLive
from tests.test_api_football import body, fixture
from tests.test_live_ingest import KICKOFF, NOW, FakeLiveAF, scheduled_match


def ev(minute, team_id, type_, detail, player, assist=None, extra=None):
    return {"time": {"elapsed": minute, "extra": extra}, "team": {"id": team_id}, "player": {"name": player},
            "assist": {"name": assist}, "type": type_, "detail": detail}  # fmt: skip


EVENTS = [
    ev(20, 505, "Goal", "Normal Goal", "Lautaro", "Barella"),
    ev(33, 489, "Card", "Yellow Card", "Tomori"),
    ev(45, 489, "Goal", "Penalty", "Pulisic", extra=2),
    ev(60, 505, "subst", "Substitution 1", "Thuram", "Arnautovic"),
    ev(71, 489, "Goal", "Own Goal", "Bastoni"),  # autogol di un interista: API-Football lo mette alla squadra che ne beneficia (verificato)
    ev(80, 489, "Card", "Red Card", "Theo"),
    ev(85, 505, "Var", "Goal cancelled", "Frattesi"),
    ev(90, 505, "Goal", "Missed Penalty", "Calhanoglu"),
]


def with_events(status="FT", goals=(1, 2)):
    item = fixture(77, (505, "Inter"), (489, "AC Milan"), date=KICKOFF, status=status, goals=goals, ht=(1, 1), league=135, season=2026)
    item["events"] = EVENTS
    return item


def test_event_kinds():
    assert event_kind("Goal", "Normal Goal") == "goal"
    assert event_kind("Goal", "Own Goal") == "own_goal"
    assert event_kind("Card", "Second Yellow card") == "second_yellow"
    assert event_kind("subst", "Substitution 3") == "subst"
    assert event_kind("Var", "Penalty confirmed") == "var"
    assert event_kind("Other", None) is None


def test_parse_events_sides_and_minutes():
    events = parse_events(with_events())
    assert [(e.minute, e.side, e.kind) for e in events][:3] == [(20, "home", "goal"), (33, "away", "yellow"), (45, "away", "penalty")]
    assert events[0].other == "Barella" and events[2].extra == 2
    assert parse_fixtures(body(with_events()))[0].events == events


def test_live_saves_commentary_and_final_marks_it_done(db):
    m = scheduled_match(db)
    live = with_events(status="2H", goals=(1, 1))
    live["fixture"]["status"]["elapsed"] = 72
    sync_live(db, FakeLiveAF(body(live), by_ids=body(live)), [135], NOW)
    assert len(db.scalars(select(MatchEvent).where(MatchEvent.match_id == m.id)).all()) == len(EVENTS)
    db.refresh(m)
    assert m.events_synced_at is None  # in corso: la cronaca può ancora cambiare

    af = FakeLiveAF(body(), by_ids=body(with_events()))
    sync_live(db, af, [135], NOW + timedelta(minutes=60))
    db.refresh(m)
    assert m.status == "finished" and m.events_synced_at is not None and db.get(MatchLive, m.id) is None
    assert len(db.scalars(select(MatchEvent).where(MatchEvent.match_id == m.id)).all()) == len(EVENTS)  # sostituita, non doppia


def test_missing_commentary_recovered_for_finished_matches(db):
    m = scheduled_match(db)
    m.status, m.home_goals, m.away_goals = "finished", 1, 2
    db.commit()
    af = FakeLiveAF(body(), by_ids=body(with_events()))
    later = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    assert sync_missing_events(db, af, later) == 1
    assert af.asked == [[77]]
    assert sync_missing_events(db, af, later) == 0  # già scaricata: nessuna nuova richiesta
    assert af.asked == [[77]]


def test_api_highlights_events_and_day(logged_client, db):
    m = scheduled_match(db)
    m.status, m.home_goals, m.away_goals = "finished", 1, 2
    db.commit()
    sync_missing_events(db, FakeLiveAF(body(), by_ids=body(with_events())), datetime(2026, 10, 25, 9, 0, tzinfo=UTC))

    groups = logged_client.get("/api/matches", params={"view": "day", "day": date(2026, 10, 24).isoformat()}).json()
    card = groups[0]["matches"][0]
    assert (card["home_goals"], card["away_goals"], card["ht_home_goals"]) == (1, 2, 1)
    assert [(h["kind"], h["player"]) for h in card["highlights"]] == [
        ("goal", "Lautaro"), ("penalty", "Pulisic"), ("own_goal", "Bastoni"), ("red", "Theo")
    ]
    assert logged_client.get("/api/matches", params={"view": "day", "day": "2026-10-25"}).json() == []
    events = logged_client.get(f"/api/matches/{m.id}/events").json()
    assert len(events) == len(EVENTS) and events[3]["kind"] == "subst"


def test_old_cached_list_never_turns_a_result_back_to_scheduled(db):
    from app.ingest.api_football import import_fixtures

    m = scheduled_match(db)
    import_fixtures(db, parse_fixtures(body(with_events())))
    db.refresh(m)
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 1, 2)
    stale = fixture(77, (505, "Inter"), (489, "AC Milan"), date=KICKOFF, status="NS", league=135, season=2026)
    import_fixtures(db, parse_fixtures(body(stale)))  # elenco in cache di prima della partita
    db.refresh(m)
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 1, 2)


def test_overdue_scheduled_match_gets_its_result(db):
    m = scheduled_match(db)  # risulta ancora "da giocare" il giorno dopo
    af = FakeLiveAF(body(), by_ids=body(with_events()))
    assert sync_missing_events(db, af, datetime(2026, 10, 25, 9, 0, tzinfo=UTC)) == 1
    db.refresh(m)
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 1, 2) and m.events_synced_at is not None


def test_football_data_fixtures_file_does_not_undo_a_result(db):
    from app.adapters.football_data import parse_csv
    from app.ingest.football_data import import_matches

    import_matches(db, parse_csv("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nI1,24/10/2026,15:00,Inter,Milan,2,1,H\n"), season="2026/27")
    import_matches(db, parse_csv("Div,Date,Time,HomeTeam,AwayTeam\nI1,24/10/2026,15:00,Inter,Milan\n"), season="2026/27")  # elenco vecchio
    m = db.scalar(select(Match))
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 2, 1)


def test_goal_cancelled_by_var_is_not_a_scorer():
    """Gol annullato per fuorigioco: resta in cronaca come annullato, non tra i marcatori, e il punteggio torna."""
    item = fixture(77, (505, "Inter"), (489, "AC Milan"), date=KICKOFF, status="FT", goals=(0, 0), league=135, season=2026)
    item["events"] = [
        ev(30, 505, "Goal", "Normal Goal", "Thuram"),
        ev(32, 505, "Var", "Goal Disallowed - offside", "Thuram"),
        ev(70, 489, "Var", "Penalty cancelled", "Leao"),  # rigore tolto: nessun gol da annullare
    ]
    events = parse_events(item)
    assert [e.kind for e in events] == ["goal_cancelled", "var", "var"]
    assert events[0].detail == "Goal Disallowed - offside"
