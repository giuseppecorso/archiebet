"""D195: Archie ricontrolla i pronostici della bacheca quando il mercato si sposta."""

from app.forecast.daily_service import recheck_leg, with_market_view

LEG = {"match_id": 1, "market": "1X2", "selection": "1", "status": "open"}


def test_market_view_is_saved_at_publication():
    fair = {1: {"1X2": {"1": 0.5, "X": 0.27, "2": 0.23}}}
    [leg] = with_market_view([LEG], fair)
    assert leg["p_market"] == 0.5 and leg["market_fav"] is True
    [other] = with_market_view([{**LEG, "selection": "X"}], fair)
    assert other["market_fav"] is False
    assert with_market_view([{**LEG, "market": "GG"}], fair) == [{**LEG, "market": "GG"}]  # mercato non provato: niente


def test_recheck_fires_when_the_pick_drops_and_the_favourite_changes():
    leg = {**LEG, "p_market": 0.45, "market_fav": True}
    found = recheck_leg(leg, {"1": 0.39, "X": 0.20, "2": 0.41})
    assert found == {"selection": "2", "p_before": 0.45, "p_now": 0.39, "p_new": 0.41}


def test_recheck_stays_quiet_otherwise():
    leg = {**LEG, "p_market": 0.45, "market_fav": True}
    assert recheck_leg(leg, {"1": 0.42, "X": 0.15, "2": 0.43}) is None  # scende solo di 3 punti
    assert recheck_leg(leg, {"1": 0.40, "X": 0.25, "2": 0.35}) is None  # scende ma resta favorito
    assert recheck_leg({**leg, "market_fav": False}, {"1": 0.30, "X": 0.2, "2": 0.5}) is None  # non era il favorito
    assert recheck_leg({**leg, "status": "won"}, {"1": 0.30, "X": 0.2, "2": 0.5}) is None  # già finita
    assert recheck_leg({**LEG}, {"1": 0.30, "X": 0.2, "2": 0.5}) is None  # schedina di prima di D195
    assert recheck_leg(leg, None) is None
