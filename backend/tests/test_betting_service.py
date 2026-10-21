from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.adapters.football_data import parse_csv
from app.auth.service import create_user
from app.betting.service import (
    BetError,
    SelectionInput,
    budget_status,
    create_bet,
    settle_open_bets,
    summarize,
    week_start,
)
from app.ingest.football_data import import_matches
from app.models import Bet, BetSnapshot, Match, MatchOdds, MatchStatus, UserSettings

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)  # mercoledì


@pytest.fixture
def world(db):
    """Un utente e tre partite di sabato 17/10/2026, con quote di chiusura sulla prima."""
    user = create_user(db, "giuse", "una-password-lunga")
    csv = (
        "Div,Date,Time,HomeTeam,AwayTeam\n"
        "I1,17/10/2026,14:00,Inter,Roma\n"
        "I1,17/10/2026,17:00,Milan,Lazio\n"
        "I1,17/10/2026,19:45,Napoli,Torino\n"
    )
    import_matches(db, parse_csv(csv), season="2026/27")
    matches = {m.home_team.name: m for m in db.scalars(select(Match))}
    inter = matches["Inter"]
    for sel, price in {"1": "2.00", "X": "3.50", "2": "4.00"}.items():
        db.add(MatchOdds(match_id=inter.id, source="football-data", bookmaker="market_avg", market="1X2", selection=sel, price=D(price), is_closing=True))
    db.commit()
    return user, matches


def finish(db, match, home, away):
    match.status, match.home_goals, match.away_goals = MatchStatus.FINISHED, home, away
    db.commit()


def test_create_bet_with_snapshot(db, world):
    user, m = world
    bet = create_bet(
        db, user.id, "real", D("10"),
        [SelectionInput(m["Inter"].id, "1X2", "1", D("2.10")), SelectionInput(m["Milan"].id, "OU2.5", "over", D("1.80"))],
        bookmaker="Snai", snapshot={"nota": "quote viste"}, now=NOW,
    )  # fmt: skip
    assert bet.total_odds == D("3.7800")
    assert bet.status == "open" and len(bet.selections) == 2
    assert db.scalar(select(BetSnapshot)).data == {"nota": "quote viste"}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"stake": D("0")}, "maggiore di zero"),
        ({"kind": "boh"}, "Tipo"),
        ({"pick": "over"}, "non valido"),
        ({"odds": D("1.00")}, "maggiore di 1"),
    ],
)
def test_invalid_bets(db, world, change, message):
    user, m = world
    sel = SelectionInput(m["Inter"].id, "1X2", change.get("pick", "1"), change.get("odds", D("2")))
    with pytest.raises(BetError, match=message):
        create_bet(db, user.id, change.get("kind", "real"), change.get("stake", D("5")), [sel], now=NOW)


def test_same_match_twice_and_started_match_rejected(db, world):
    user, m = world
    twice = [SelectionInput(m["Inter"].id, "1X2", "1", D("2")), SelectionInput(m["Inter"].id, "GG", "yes", D("1.8"))]
    with pytest.raises(BetError, match="due volte"):
        create_bet(db, user.id, "real", D("5"), twice, now=NOW)
    after_kickoff = datetime(2026, 10, 17, 14, 30, tzinfo=UTC)
    with pytest.raises(BetError, match="già iniziata"):
        create_bet(db, user.id, "real", D("5"), [SelectionInput(m["Inter"].id, "1X2", "1", D("2"))], now=after_kickoff)


def test_settle_won_bet_with_clv(db, world):
    user, m = world
    bet = create_bet(
        db, user.id, "real", D("10"),
        [SelectionInput(m["Inter"].id, "1X2", "1", D("2.20")), SelectionInput(m["Milan"].id, "GG", "yes", D("1.75"))],
        now=NOW,
    )  # fmt: skip
    finish(db, m["Inter"], 2, 0)
    assert settle_open_bets(db, NOW) == 0  # Milan-Lazio non è finita: schedina ancora aperta
    db.refresh(bet)
    inter_sel = bet.selections[0]
    assert inter_sel.status == "won"
    # Chiusura 2.00/3.50/4.00 senza margine: quota giusta del "1" = 2.0714 → CLV 2.20/2.0714 - 1 = +6,21%
    assert inter_sel.fair_closing_odds == D("2.071")
    assert inter_sel.clv == D("0.0621")

    finish(db, m["Milan"], 1, 1)
    assert settle_open_bets(db, NOW) == 1
    db.refresh(bet)
    assert (bet.status, bet.payout) == ("won", D("38.50"))  # 10 × 2,20 × 1,75
    assert bet.selections[1].clv is None  # niente quote di chiusura per il Goal


def test_one_lost_selection_closes_the_bet(db, world):
    user, m = world
    bet = create_bet(
        db, user.id, "simulated", D("5"),
        [SelectionInput(m["Inter"].id, "1X2", "2", D("4.00")), SelectionInput(m["Milan"].id, "1X2", "1", D("2.00"))],
        now=NOW,
    )  # fmt: skip
    finish(db, m["Inter"], 2, 0)
    assert settle_open_bets(db, NOW) == 1
    db.refresh(bet)
    assert (bet.status, bet.payout) == ("lost", D("0"))


def test_cancelled_match_is_void(db, world):
    user, m = world
    bet = create_bet(db, user.id, "real", D("10"), [SelectionInput(m["Napoli"].id, "1X2", "1", D("1.50"))], now=NOW)
    m["Napoli"].status = MatchStatus.CANCELLED
    db.commit()
    settle_open_bets(db, NOW)
    db.refresh(bet)
    assert (bet.status, bet.payout) == ("void", D("10.00"))


def test_week_starts_on_monday_in_italy():
    # Domenica 18/10 alle 23:30 italiane = 21:30 UTC: la settimana è iniziata lunedì 12/10 alle 00:00 italiane
    assert week_start(datetime(2026, 10, 18, 21, 30, tzinfo=UTC)) == datetime(2026, 10, 11, 22, 0, tzinfo=UTC)


def test_budget_warns_only_for_real_bets(db, world):
    user, m = world
    db.add(UserSettings(user_id=user.id, weekly_budget=D("20"), monthly_budget=D("100")))
    db.commit()
    create_bet(db, user.id, "simulated", D("50"), [SelectionInput(m["Inter"].id, "1X2", "1", D("2"))], now=NOW)
    assert budget_status(db, user.id, NOW).warnings == []  # le simulate non contano
    create_bet(db, user.id, "real", D("15"), [SelectionInput(m["Milan"].id, "1X2", "1", D("2"))], now=NOW)
    create_bet(db, user.id, "real", D("10"), [SelectionInput(m["Napoli"].id, "1X2", "1", D("2"))], now=NOW)
    status = budget_status(db, user.id, NOW)
    assert status.week_staked == D("25")
    assert len(status.warnings) == 1 and "settimana" in status.warnings[0]


def test_summary(db, world):
    user, m = world
    create_bet(db, user.id, "real", D("10"), [SelectionInput(m["Inter"].id, "1X2", "1", D("2.20"))], now=NOW)
    create_bet(db, user.id, "real", D("10"), [SelectionInput(m["Milan"].id, "1X2", "1", D("2.00"))], now=NOW)
    create_bet(db, user.id, "real", D("5"), [SelectionInput(m["Napoli"].id, "1X2", "1", D("1.50"))], now=NOW)
    finish(db, m["Inter"], 1, 0)
    finish(db, m["Milan"], 0, 1)
    settle_open_bets(db, NOW)
    s = summarize(db.scalars(select(Bet)).all())
    assert (s.bets, s.open, s.settled, s.won) == (3, 1, 2, 1)
    assert (s.staked, s.returned, s.profit) == (D("20"), D("22.00"), D("2.00"))
    assert s.roi == 0.1 and s.win_rate == 0.5
    assert s.avg_clv == 0.0621 and s.clv_count == 1


def test_clv_filled_when_closing_arrives_later(db, world):
    """La schedina si chiude a fine partita; la chiusura di Pinnacle arriva al giro dopo: il CLV si riempie allora."""
    from app.betting.service import fill_missing_clv

    user, m = world
    bet = create_bet(db, user.id, "simulated", D("10"), [SelectionInput(m["Milan"].id, "GG", "yes", D("2.00"))], now=NOW)
    finish(db, m["Milan"], 1, 1)
    after = datetime(2026, 10, 17, 20, 0, tzinfo=UTC)
    assert settle_open_bets(db, after) == 1
    db.refresh(bet)
    assert bet.selections[0].clv is None  # chiusura non ancora arrivata
    for sel, price in {"yes": "1.90", "no": "1.90"}.items():
        db.add(MatchOdds(match_id=m["Milan"].id, source="oddspapi", bookmaker="pinnacle", market="GG", selection=sel, price=D(price), is_closing=True))
    db.commit()
    assert fill_missing_clv(db, after) == 1
    db.commit()
    db.refresh(bet)
    assert bet.selections[0].clv == D("0.0000")  # 2,00 contro la quota giusta 2,00
