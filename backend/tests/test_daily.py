"""Bacheca Daily (D153): quando escono le schedine, come si chiudono, statistiche, pubblicazione."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.forecast.daily import DONE, LOST, OPEN, VOID, WON, due, leg_status, profit, slip_status, stats

FRIDAY_9 = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)  # venerdì 9:00 in Italia
FRIDAY_11 = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)  # venerdì 11:00
MONDAY_11 = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


def test_publication_calendar():
    assert due(FRIDAY_9) == []  # prima delle 10 niente
    friday = {k.key: (period, end) for k, period, _, end in due(FRIDAY_11)}
    assert set(friday) == {"giorno", "weekend", "colpo", "clv"}  # il venerdì esce anche il weekend
    assert friday["weekend"][1].date().isoformat() == "2026-11-01"  # fino a domenica
    assert friday["giorno"][0] == "2026-10-30"
    monday = {k.key: end for k, _, _, end in due(MONDAY_11)}
    assert "settimana" in monday and "weekend" not in monday
    assert monday["settimana"].date().isoformat() == "2026-11-08"


def test_leg_and_slip_status():
    assert leg_status("finished", WON) == WON and leg_status("scheduled", None) == OPEN and leg_status("cancelled", None) == VOID
    legs = lambda *s: [{"status": x, "price": 2.0, "p": 0.5} for x in s]  # noqa: E731
    assert slip_status(legs(WON, OPEN), False) == OPEN
    assert slip_status(legs(WON, LOST, OPEN), False) == LOST  # persa al primo errore
    assert slip_status(legs(WON, VOID), False) == WON
    assert slip_status(legs(WON, OPEN), True) == OPEN and slip_status(legs(WON, LOST), True) == DONE


def test_profit_with_one_euro():
    two = [{"status": WON, "price": 2.0}, {"status": VOID, "price": 3.0}]
    assert profit(two, WON, 6.0, False) == pytest.approx(1.0)  # il nullo vale quota 1
    assert profit(two, LOST, 6.0, False) == -1.0
    singles = [{"status": WON, "price": 2.5}, {"status": LOST, "price": 1.8}, {"status": OPEN, "price": 2.0}]
    assert profit(singles, DONE, 1.0, True) == pytest.approx(0.5)


@dataclass
class S:
    kind: str
    legs: list
    status: str
    total_odds: float
    win_probability: float


def test_stats_compare_hits_with_expected():
    won = S("giorno", [{"status": WON, "p": 0.7, "price": 1.5}] * 2, WON, 2.25, 0.49)
    lost = S("giorno", [{"status": WON, "p": 0.7, "price": 1.5}, {"status": LOST, "p": 0.7, "price": 1.5}], LOST, 2.25, 0.49)
    clv = S("clv", [{"status": WON, "p": 0.4, "price": 2.8}, {"status": LOST, "p": 0.5, "price": 2.1}], DONE, 1.0, 0.45)
    st = stats([won, lost, clv, S("giorno", [{"status": OPEN, "p": 0.6, "price": 1.6}], OPEN, 1.6, 0.6)])
    g = st["giorno"]
    assert (g.published, g.closed, g.won, g.legs_won, g.legs_closed) == (3, 2, 1, 3, 4)
    assert g.expected == pytest.approx(0.98) and g.profit == pytest.approx(1.25 - 1)
    c = st["clv"]
    assert (c.won, c.expected) == (1, pytest.approx(0.9)) and c.profit == pytest.approx(1.8 - 1)


def _pick(market, selection, p, level, prices=None):
    return {"market": market, "selection": selection, "level": level, "event": f"{market} {selection}", "p_model": p, "p_archie": p,
            "evidence": [5, 10, 5, 10], "reasons": [], "prices": prices or {}, "traits": [], "caution": []}  # fmt: skip


def test_publish_once_and_settle_from_the_study(db):
    from datetime import timedelta

    from app.forecast.daily_service import publish_due, settle_daily
    from app.ingest.teams import ensure_competitions
    from app.models import DailySlip, Match, MatchStatus, MatchStudy, Team

    comps = ensure_competitions(db)
    teams = [Team(name=n, country="Italia") for n in ("Inter", "Milan", "Roma", "Lazio")]
    db.add_all(teams)
    db.flush()
    games = [Match(competition_id=comps["ITA-A"].id, season="2026/27", home_team_id=h.id, away_team_id=a.id, kickoff_at=FRIDAY_11 + timedelta(hours=h_off),
                   status=MatchStatus.SCHEDULED) for h, a, h_off in ((teams[0], teams[1], 6), (teams[2], teams[3], 8))]  # fmt: skip
    db.add_all(games)
    db.flush()
    db.add(MatchStudy(match_id=games[0].id, computed_at=FRIDAY_11, data={"picks": [_pick("GG", "yes", 0.66, "equilibrato", {"sisal": 1.7})]}))
    db.add(MatchStudy(match_id=games[1].id, computed_at=FRIDAY_11, data={"picks": [_pick("OU2.5", "under", 0.6, "equilibrato")]}))
    db.commit()

    published = publish_due(db, FRIDAY_11)
    assert "giorno" in published and "weekend" in published
    assert publish_due(db, FRIDAY_11 + timedelta(hours=1)) == []  # una sola per tipo e giorno: non cambia più
    slip = db.query(DailySlip).filter_by(kind="giorno").one()
    assert [leg["market"] for leg in slip.legs] == ["GG", "OU2.5"]  # 0,66 × 0,60 = 0,40 ≥ 20%: tutte e due
    assert slip.total_odds == round(1.7 * round(1 / 0.6, 2), 2) and slip.win_probability == pytest.approx(0.396)

    games[0].status, games[0].home_goals, games[0].away_goals = MatchStatus.FINISHED, 2, 1
    db.commit()
    assert settle_daily(db) == 0  # la seconda partita è ancora da giocare
    games[1].status, games[1].home_goals, games[1].away_goals = MatchStatus.FINISHED, 3, 0
    db.commit()
    assert settle_daily(db) >= 1
    db.refresh(slip)
    assert [leg["status"] for leg in slip.legs] == ["won", "lost"] and slip.status == "lost"  # 3 gol: l'Under 2.5 perde


def test_daily_api_board_and_stats(logged_client, db):
    from app.models import DailySlip

    leg = {"match_id": 1, "kickoff_at": "2026-10-30T18:00:00+00:00", "competition": "Serie A", "home": "Inter", "away": "Milan",
           "market": "GG", "selection": "yes", "event": "segnano entrambe", "p": 0.66, "price": 1.7, "status": "won"}  # fmt: skip
    db.add(DailySlip(kind="giorno", period="2026-10-29", published_at=FRIDAY_9, legs=[leg], total_odds=1.7, win_probability=0.66, status="won"))
    db.add(DailySlip(kind="giorno", period="2026-10-30", published_at=FRIDAY_11, legs=[{**leg, "status": "open"}], total_odds=1.7, win_probability=0.66, status="open"))
    db.commit()
    body = logged_client.get("/api/daily").json()
    [board] = body["board"]
    assert board["period"] == "2026-10-30" and board["title"] == "La schedina del giorno"  # sulla bacheca l'ultima
    giorno = next(s for s in body["stats"] if s["kind"] == "giorno")
    assert (giorno["published"], giorno["won"], giorno["profit"]) == (2, 1, pytest.approx(0.7))
    assert [h["period"] for h in body["history"]] == ["2026-10-29"]
