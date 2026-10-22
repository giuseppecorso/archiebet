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


# --- Gol di una squadra e Draw No Bet (D135) ---


def test_team_goals_and_draw_no_bet_settle_on_the_score():
    from app.betting.calc import VOID

    assert selection_outcome("TGH1.5", "over", 2, 0) == WON
    assert selection_outcome("TGA0.5", "under", 2, 1) == LOST
    assert selection_outcome("DNB", "1", 1, 1) == VOID  # pareggio: puntata restituita
    assert selection_outcome("DNB", "2", 0, 1) == WON
    assert market_name("TGA0.5") == "gol ospite Under/Over 0.5" and market_name("DNB") == "Draw No Bet"
    assert is_valid_pick("TGH2.5", "under") and is_valid_pick("DNB", "2") and not is_valid_pick("DNB", "X")


def test_draw_no_bet_fair_closing_and_live():
    from app.betting.calc import fair_closing_odds

    # 1X2 2,00 / 3,50 / 4,00 senza margine: P(1) 48,3%, P(2) 24,1% → DNB "1" = 2/3 → quota giusta 1,50
    assert float(fair_closing_odds("DNB", "1", {"1": D("2.0"), "X": D("3.5"), "2": D("4.0")}, None)) == pytest.approx(1.5)
    probs = outcome_probabilities(1.6, 1.0)
    assert selection_probability("DNB", "2", probs) == pytest.approx(probs["2"] + probs["X"])  # viva anche col pareggio
    assert selection_probability("TGH0.5", "over", probs) == pytest.approx(1 - 2.718281828 ** -1.6, abs=1e-6)
    assert outcome_probabilities(0.4, 0.4, 2, 0)["home_over1.5"] == pytest.approx(1.0)


TEAM_BOOK = {
    "pinnacle": {"1X2": {"1": 2.0, "X": 3.6, "2": 4.0}, "TGH1.5": {"over": 2.10, "under": 1.75}, "TGA0.5": {"over": 1.40, "under": 2.90}},
    "sisal": {"1X2": {"1": 1.95, "X": 3.4, "2": 3.9}, "TGH1.5": {"over": 2.20, "under": 1.62}, "DNB": {"1": 1.38, "2": 2.70}},
}


def test_team_goals_in_every_league_and_dnb_from_1x2():
    probs = best_probabilities(TEAM_BOOK, None)  # niente bisogno di statistiche: si chiudono col risultato
    assert probs["TGH1.5"][0] == "pinnacle" and "TGA0.5" in probs
    p1x2 = probs["1X2"][1]
    assert probs["DNB"][1]["1"] == pytest.approx(p1x2["1"] / (p1x2["1"] + p1x2["2"]))
    markets = [p.market for p in match_picks(TEAM_BOOK, None, ["sisal"])]
    assert markets.index("DNB") < markets.index("TGH1.5") < markets.index("TGA0.5")
    assert market_family("TGH1.5") == "gol squadra" and market_family("DNB") == "esito"


def test_draw_no_bet_never_in_multiples():
    from types import SimpleNamespace

    from app.forecast.picks_service import legs_for

    match = SimpleNamespace(id=1, kickoff_at=NOW)
    picks = [(match, match_picks(TEAM_BOOK, None, ["sisal"]))]
    markets = {leg.market for leg in legs_for(picks, "sisal", bench=frozenset())}
    assert "TGH1.5" in markets and "DNB" not in markets
