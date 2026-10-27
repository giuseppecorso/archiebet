from datetime import UTC, date, datetime

from app.forecast.history_sim import Estimate, Play
from app.forecast.occasion_test import Checked, Comparison, check, compare, split
from app.forecast.history_sim import SimMatch


def play(mid, clv, season="2023/24", sel="1"):
    return Play(mid, season, "ITA-A", "1X2", sel, 2.2, 0.05, clv, True)


def test_confirmed_means_study_at_least_as_sure_as_pinnacle():
    assert Checked(play(1, 0.02), 0.50, 0.48).confirmed
    assert Checked(play(1, 0.02), 0.48, 0.48).confirmed
    assert not Checked(play(1, 0.02), 0.40, 0.48).confirmed


def test_compare_and_pass_rule():
    rows = [Checked(play(k, 0.05 + 0.001 * (k % 3)), 0.6, 0.5) for k in range(40)] + [Checked(play(100 + k, -0.01 + 0.001 * (k % 3)), 0.3, 0.5) for k in range(40)]
    c = compare(rows)
    assert abs(c.difference - 0.06) < 1e-9 and c.passed
    assert not Comparison(Estimate(0.03, 0.01, 50, 50), Estimate(0.02, 0.01, 50, 50)).passed  # differenza dentro il rumore
    assert not Comparison(Estimate(0.01, 0.01, 50, 50), Estimate(-0.05, 0.01, 50, 50)).passed  # confermate non sopra zero


def test_check_attaches_study_and_split_by_season():
    k = datetime(2024, 3, 1, 15, tzinfo=UTC)
    fair = {"1X2": {"1": 0.5, "X": 0.27, "2": 0.23}}
    m = SimMatch(7, "2025/26", "ITA-A", date(2024, 3, 1), k, 2, 0, fair, fair, {"1X2": {"1": 2.2, "X": 3.6, "2": 4.3}})
    rows = check([m], {7: {"1X2": {"1": 0.55, "X": 0.25, "2": 0.20}}})
    assert [(r.play.selection, r.confirmed) for r in rows] == [("1", True)]  # 0,5 × 2,2 − 1 = +10%: occasione
    assert check([m], {}) == []  # senza studio niente
    tuning, confirmation = split(rows)
    assert tuning == [] and len(confirmation) == 1
