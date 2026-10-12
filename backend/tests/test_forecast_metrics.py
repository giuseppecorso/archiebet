"""Misure di qualità, prob. senza margine e cassaforte: valori calcolati a mano."""

from datetime import datetime

import numpy as np
import pytest

from app.forecast.data import fair_probabilities
from app.forecast.metrics import brier, calibration, expected_calibration_error, log_loss, outcome_index, rps
from app.forecast.vault import VaultLockedError, ensure_can_evaluate, is_vault_season, open_vault, vault_is_open

PROBS = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
OUTCOMES = np.array([0, 1])  # vince la casa, poi pareggio


def test_outcome_index():
    assert [outcome_index(2, 1), outcome_index(1, 1), outcome_index(0, 3)] == [0, 1, 2]


def test_log_loss_by_hand():
    assert log_loss(PROBS, OUTCOMES) == pytest.approx(-(np.log(0.5) + np.log(0.3)) / 2)


def test_brier_by_hand():
    # (0,5−1)² + 0,3² + 0,2² = 0,38 ; 0,2² + (0,3−1)² + 0,5² = 0,78
    assert brier(PROBS, OUTCOMES) == pytest.approx((0.38 + 0.78) / 2)


def test_rps_by_hand_and_ordering():
    assert rps(PROBS, OUTCOMES) == pytest.approx(0.145)
    # Vince la casa: aver detto "pareggio sicuro" è meno grave di "vince l'ospite sicuro"
    assert rps(np.array([[0, 1, 0]]), np.array([0])) == pytest.approx(0.5)
    assert rps(np.array([[0, 0, 1]]), np.array([0])) == pytest.approx(1.0)


def test_calibration_by_hand():
    table = calibration(np.array([0.05, 0.15, 0.18, 1.0]), np.array([0, 1, 0, 1]))
    assert [(b.low, b.count) for b in table] == [(0.0, 1), (pytest.approx(0.1), 2), (pytest.approx(0.9), 1)]
    assert table[1].predicted == pytest.approx(0.165) and table[1].observed == pytest.approx(0.5)
    # ECE = (1·0,05 + 2·0,335 + 1·0) / 4
    assert expected_calibration_error(table) == pytest.approx(0.72 / 4)


def test_fair_probabilities_remove_the_margin():
    assert fair_probabilities(1.9, 3.8, 3.8) == pytest.approx((0.5, 0.25, 0.25))


def test_vault_is_locked_until_opened(tmp_path):
    marker = tmp_path / "vault_opened.txt"
    assert is_vault_season("2025/26") and is_vault_season("2026/27") and not is_vault_season("2024/25")
    ensure_can_evaluate(["2023/24", "2024/25"], marker)  # nessun errore
    with pytest.raises(VaultLockedError, match="2025/26"):
        ensure_can_evaluate(["2024/25", "2025/26"], marker)
    open_vault(datetime(2027, 6, 1), marker)
    assert vault_is_open(marker)
    ensure_can_evaluate(["2025/26"], marker)
