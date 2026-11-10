import math

import pytest

from app.forecast import movement_test as mt


def obs(mid, sel, p_open, p_close, won, price=2.0, b365=None, market="1X2", season="2015/16"):
    return mt.Obs(mid, season, market, sel, p_open, p_close, won, price, b365)


def test_move_is_close_minus_open():
    assert obs(1, "1", 0.40, 0.46, True).move == pytest.approx(0.06)


def test_slope_matches_ordinary_least_squares():
    # y = vinto − p_close: (1−0.5)=0.5, (0−0.5)=−0.5, (1−0.5)=0.5, (0−0.5)=−0.5 ; x = 0.1, −0.1, 0.05, −0.05
    data = [obs(1, "1", 0.4, 0.5, True), obs(2, "1", 0.6, 0.5, False), obs(3, "1", 0.45, 0.5, True), obs(4, "1", 0.55, 0.5, False)]
    s = mt.slope(data)
    # pendenza = Σxy / Σx² = (0.05+0.05+0.025+0.025) / (0.01+0.01+0.0025+0.0025) = 0.15 / 0.025 = 6
    assert s.beta == pytest.approx(6.0)
    assert s.clusters == 4 and s.n == 4


def test_slope_standard_error_counts_matches_not_outcomes():
    one = [obs(m, "1", 0.4 + 0.01 * (m % 3), 0.45, m % 2 == 0) for m in range(40)]
    doubled = one + [obs(o.match_id, "2", o.p_open, o.p_close, o.won) for o in one]  # stesso esito copiato nella stessa partita
    a, b = mt.slope(one), mt.slope(doubled)
    assert b.beta == pytest.approx(a.beta)
    # copiare le osservazioni dentro la stessa partita non deve far sembrare la stima più sicura
    assert b.std_error == pytest.approx(a.std_error)
    assert math.isfinite(a.std_error) and a.std_error > 0


def test_slope_needs_some_movement():
    assert mt.slope([obs(1, "1", 0.5, 0.5, True), obs(2, "1", 0.5, 0.5, False), obs(3, "1", 0.5, 0.5, True)]) is None


def test_plays_pick_the_biggest_move_in_the_direction():
    match = [obs(1, "1", 0.40, 0.47, True), obs(1, "X", 0.30, 0.28, False), obs(1, "2", 0.30, 0.25, False)]
    follow = mt.plays(match, +1, 0.04)
    against = mt.plays(match, -1, 0.04)
    assert [o.selection for o in follow] == ["1"]
    assert [o.selection for o in against] == ["2"]
    assert mt.plays(match, -1, 0.06) == []


def test_plays_one_per_match_and_market():
    data = [obs(1, "1", 0.4, 0.5, True), obs(1, "over", 0.5, 0.6, True, market="OU2.5"), obs(2, "1", 0.4, 0.41, True)]
    chosen = mt.plays(data, +1, 0.02)
    assert sorted((o.match_id, o.market) for o in chosen) == [(1, "1X2"), (1, "OU2.5")]


def test_roi_at_pinnacle_and_bet365_closing_prices():
    chosen = [obs(1, "1", 0.4, 0.5, True, price=2.1, b365=2.0), obs(2, "1", 0.4, 0.5, False, price=1.9, b365=None)]
    pin = mt.roi(chosen)
    assert pin.mean == pytest.approx((1.1 - 1.0) / 2)
    b365 = mt.roi(chosen, "bet365")
    assert b365.n == 1 and b365.mean == pytest.approx(1.0)
    assert mt.roi([]) is None


def test_threshold_needs_enough_plays():
    few = [obs(m, "1", 0.4, 0.5, True) for m in range(10)]
    assert mt.choose_threshold(few, +1) == (None, None)


def test_run_follows_the_sign_found_in_tuning():
    # In taratura chi si muove in su vince più del previsto: direzione "seguire"
    tuning = []
    for m in range(400):
        up = m % 2 == 0
        tuning += [obs(m, "1", 0.40, 0.45 if up else 0.35, up if m % 4 else not up, price=2.0)]
    res = {r.market: r for r in mt.run(tuning, tuning)}["1X2"]
    assert res.direction == 1
    assert res.tuning_slope.beta > 0
