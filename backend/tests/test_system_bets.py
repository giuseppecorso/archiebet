from decimal import Decimal

import pytest

from app.betting.calc import LOST, OPEN, VOID, WON, at_least, system_combinations, system_payout, system_range, system_status

D = Decimal


def test_combinations():
    assert system_combinations(6, 4) == 15
    assert system_combinations(3, 2) == 3
    with pytest.raises(ValueError):
        system_combinations(3, 4)


def test_status_closes_as_lost_as_soon_as_no_combination_can_win():
    assert system_status([LOST, LOST, LOST, OPEN, OPEN, OPEN], 4) == LOST  # 3 sbagliate su 6: nessuna quaterna buona
    assert system_status([LOST, LOST, OPEN, OPEN, OPEN, OPEN], 4) == OPEN
    assert system_status([WON, WON, WON, WON, LOST, LOST], 4) == WON
    assert system_status([VOID, VOID, VOID], 2) == VOID


def test_payout_2_of_3_by_hand():
    # 9 € su 3 doppie (3 € l'una): quote 2, 3, 4; la terza persa -> paga solo la doppia 2 x 3
    sels = [(WON, D("2")), (WON, D("3")), (LOST, D("4"))]
    assert system_payout(D("9"), sels, 2) == D("18.00")
    # tutte vinte: 3 × (6 + 8 + 12) = 78
    assert system_payout(D("9"), [(WON, D("2")), (WON, D("3")), (WON, D("4"))], 2) == D("78.00")
    # annullata = quota 1: doppie 2x1, 2x4 (persa la terza? no: qui la terza vince) -> 3 × (2 + 8 + 4) = 42
    assert system_payout(D("9"), [(WON, D("2")), (VOID, D("3")), (WON, D("4"))], 2) == D("42.00")
    assert system_payout(D("9"), [(LOST, D("2")), (LOST, D("3")), (WON, D("4"))], 2) == D("0.00")
    with pytest.raises(ValueError):
        system_payout(D("9"), [(WON, D("2")), (OPEN, D("3")), (WON, D("4"))], 2)


def test_range_min_and_max():
    low, high = system_range(D("9"), [D("2"), D("3"), D("4")], 2)
    assert low == D("18.00") and high == D("78.00")


def test_at_least_exact():
    assert at_least([0.5, 0.5], 1) == pytest.approx(0.75)
    assert at_least([0.5, 0.5, 0.5], 2) == pytest.approx(0.5)
    assert at_least([0.9, 0.8, 0.7], 3) == pytest.approx(0.9 * 0.8 * 0.7)
    assert at_least([0.3], 0) == pytest.approx(1.0)

