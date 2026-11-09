"""Bacheca da 1,40 (D172): il filtro usa il prezzo che si troverebbe davvero."""

import pytest

from app.forecast.daily import KINDS
from app.forecast.daily_service import best_value, choose_study_legs
from app.forecast.daily_variants import before_d172
from app.forecast.study import playable_price


def pick(p: float, level: str = "equilibrato", price: float | None = None) -> dict:
    return {"market": "OU2.5", "selection": "over", "level": level, "p_model": p, "p_archie": p, "evidence": [6, 10, 6, 10],
            "prices": {"sisal": price} if price else {}, "traits": [], "caution": []}  # fmt: skip


def test_the_real_price_wins_over_the_estimate():
    assert playable_price(pick(0.5, price=1.9)) == 1.9


def test_without_a_real_price_the_margin_is_removed():
    assert playable_price(pick(0.5)) == pytest.approx(0.94 / 0.5)


def test_picks_below_the_minimum_never_reach_the_slip():
    low, ok = pick(0.71), pick(0.60)  # stimate 1,32 e 1,57
    assert [mid for mid, _ in choose_study_legs(KINDS["giorno"], [(1, [low]), (2, [ok])])] == [2]


def test_a_real_price_above_the_minimum_keeps_the_pick():
    assert [mid for mid, _ in choose_study_legs(KINDS["giorno"], [(1, [pick(0.71, price=1.45)])])] == [1]


def test_the_week_slip_now_draws_from_the_balanced_level():
    assert KINDS["settimana"].level == "equilibrato"
    assert [mid for mid, _ in choose_study_legs(KINDS["settimana"], [(1, [pick(0.60)])])] == [1]


def test_the_old_board_had_no_minimum():
    assert [mid for mid, _ in before_d172(KINDS["giorno"], [(1, [pick(0.71)])])] == [1]


def test_the_clv_slip_keeps_its_rule():
    b = {"pinnacle": {"1X2": {"1": 1.8, "X": 3.6, "2": 4.8}}, "bet365": {"1X2": {"1": 1.95, "X": 3.2, "2": 4.2}}}
    assert [c.selection for _, c in best_value(KINDS["clv"], [(1, b)], ("bet365",))] == ["1"]


def test_the_from_two_slip_is_gone():
    assert "da_due" not in KINDS
