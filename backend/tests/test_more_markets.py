"""Mercati in più (D131): Under/Over 0.5 e 4.5, angoli e cartellini in Pronostici, multipla, schedina e chiusura."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.adapters.football_data import parse_csv
from app.auth.service import create_user
from app.betting.calc import LOST, WON, is_valid_pick, market_name, secondary_outcome, selection_outcome
from app.betting.service import SelectionInput, create_bet, settle_open_bets
from app.forecast.live import LegState, leg_probability, outcome_probabilities, selection_probability
from app.forecast.picks import best_probabilities, market_family, match_picks
from app.ingest.football_data import import_matches
from app.models import Match, MatchOdds, MatchStatus

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def test_new_markets_are_valid_and_named():
    assert is_valid_pick("OU0.5", "over") and is_valid_pick("OU4.5", "under")
    assert is_valid_pick("CORH4.5", "over") and is_valid_pick("CRD3.5", "under")
    assert not is_valid_pick("COR9.5", "yes")
    assert market_name("OU4.5") == "Under/Over 4.5"
    assert market_name("COR9.5") == "angoli Under/Over 9.5"
    assert market_name("CRDA1.5") == "cartellini ospite Under/Over 1.5"


def test_goal_lines_settle_on_the_score():
    assert selection_outcome("OU0.5", "under", 0, 0) == WON
    assert selection_outcome("OU4.5", "over", 3, 2) == WON
    assert selection_outcome("OU4.5", "over", 2, 2) == LOST
    with pytest.raises(ValueError):
        selection_outcome("COR9.5", "over", 1, 0)  # gli angoli non si chiudono con il risultato


def test_secondary_outcome_waits_for_stats():
    # 6 + 4 = 10 angoli; cartellini: 2 gialli + 1 rosso per la casa = 3
    assert secondary_outcome("COR9.5", "over", (6, 4), (2, 1), (1, 0)) == WON
    assert secondary_outcome("CRDH2.5", "under", (6, 4), (2, 1), (1, 0)) == LOST
    assert secondary_outcome("COR9.5", "over", (None, None), (None, None), (None, None)) is None


def test_live_probability_of_extra_goal_lines():
    probs = outcome_probabilities(1.4, 1.1)
    assert selection_probability("OU0.5", "over", probs) == pytest.approx(probs["over0.5"])
    assert selection_probability("OU4.5", "under", probs) == pytest.approx(1 - probs["over4.5"])
    assert probs["over0.5"] > probs["over1.5"] > probs["over"] > probs["over3.5"] > probs["over4.5"]
    # Con 1-0 l'Over 0.5 è già vinto
    assert outcome_probabilities(0.5, 0.5, 1, 0)["over0.5"] == pytest.approx(1.0)
    # Angoli: nessun modello dal vivo
    assert leg_probability(LegState("COR9.5", "over", (1.4, 1.1), "1H", 20, 0, 0)) is None


BOOK = {
    "pinnacle": {"1X2": {"1": 2.0, "X": 3.6, "2": 4.0}, "COR9.5": {"over": 1.80, "under": 2.05}, "COR5.5": {"over": 1.02, "under": 12.0}},
    "sisal": {"1X2": {"1": 1.95, "X": 3.4, "2": 3.9}, "COR9.5": {"over": 1.85, "under": 1.85}, "CRD3.5": {"over": 1.70, "under": 2.00}},
    "eurobet": {"CRD3.5": {"over": 1.75, "under": 1.95}},
}


def test_corners_and_cards_only_where_they_can_be_settled():
    assert not any(m.startswith(("COR", "CRD")) for m in best_probabilities(BOOK, None))
    probs = best_probabilities(BOOK, None, secondary=True)
    assert probs["COR9.5"][0] == "pinnacle"
    assert probs["CRD3.5"][0] == "consenso"  # niente Pinnacle: media di Sisal ed Eurobet
    assert "COR5.5" not in probs  # linea fuori dal 12-88%: non si propone
    markets = [p.market for p in match_picks(BOOK, None, ["sisal"], secondary=True)]
    assert markets.index("1X2") < markets.index("COR9.5") < markets.index("CRD3.5")


def test_market_families():
    assert [market_family(m) for m in ("1X2", "DC", "OU4.5", "GG", "CORH4.5", "CRD3.5")] == ["esito", "esito", "gol", "gol", "angoli", "cartellini"]


@pytest.fixture
def world(db):
    user = create_user(db, "giuse", "una-password-lunga")
    import_matches(db, parse_csv("Div,Date,Time,HomeTeam,AwayTeam\nI1,17/10/2026,14:00,Inter,Roma\n"), season="2026/27")
    match = db.scalar(select(Match))
    for sel, price in {"over": "1.80", "under": "2.05"}.items():
        db.add(MatchOdds(match_id=match.id, source="oddspapi", bookmaker="pinnacle", market="COR9.5", selection=sel, price=D(price), is_closing=True))
    db.commit()
    return user, match


def test_corner_bet_settles_when_stats_arrive(db, world):
    user, match = world
    bet = create_bet(db, user.id, "simulated", D("10"), [SelectionInput(match.id, "COR9.5", "over", D("1.90"))], now=NOW)
    match.status, match.home_goals, match.away_goals = MatchStatus.FINISHED, 1, 0
    db.commit()
    after = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)
    assert settle_open_bets(db, after) == 0  # angoli non ancora arrivati
    match.home_corners, match.away_corners = 7, 5
    match.home_yellow = match.away_yellow = match.home_red = match.away_red = 0
    db.commit()
    assert settle_open_bets(db, after) == 1
    db.refresh(bet)
    assert (bet.status, bet.payout) == ("won", D("19.00"))
    assert bet.selections[0].clv is not None  # chiusura di Pinnacle sugli angoli


def test_corner_bet_void_if_stats_never_arrive(db, world):
    user, match = world
    bet = create_bet(db, user.id, "simulated", D("10"), [SelectionInput(match.id, "COR9.5", "over", D("1.90"))], now=NOW)
    match.status, match.home_goals, match.away_goals = MatchStatus.FINISHED, 1, 0
    db.commit()
    assert settle_open_bets(db, datetime(2026, 10, 17, 12, tzinfo=UTC) + timedelta(days=15)) == 1
    db.refresh(bet)
    assert (bet.status, bet.payout) == ("void", D("10.00"))
