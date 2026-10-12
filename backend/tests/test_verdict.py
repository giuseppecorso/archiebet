"""Verdetto: si calcola solo a cassaforte aperta e applica i criteri fissati in anticipo (D58)."""

from dataclasses import replace
from datetime import datetime

import pytest

from app.forecast.backtest import Scores
from app.forecast.factor_test import Clv
from app.forecast.vault import VaultLockedError, open_vault
from app.forecast.verdict import Verdict, compute, sharp_opening
from tests.test_backtest import _league

SCORES = Scores(n=100, log_loss=1.0, brier=0.6, rps=0.2, ece=0.02, n_market=100, model_log_loss_on_market=1.02, market_log_loss=1.0)


def test_verdict_refused_while_vault_is_closed(tmp_path):
    with pytest.raises(VaultLockedError):
        compute(_league(["2024/25", "2025/26"]), {}, {}, {}, vault_marker=tmp_path / "chiusa")


def test_verdict_runs_on_vault_seasons_once_opened(tmp_path):
    marker = tmp_path / "aperta"
    open_vault(datetime(2027, 6, 1), marker)
    games = _league(["2024/25", "2025/26"])
    v = compute(games, {}, {}, {}, vault_marker=marker)
    assert v.seasons == ["2025/26"]
    assert v.model.n == 30
    assert v.radar is None  # niente quote nei dati finti


def test_criteria_fixed_in_advance():
    good = Verdict(["2025/26"], SCORES, Clv(n=200, mean=0.03, std_error=0.01))
    assert good.model_calibrated and good.model_close_to_market and good.radar_passes
    assert not replace(good, model=replace(SCORES, ece=0.031)).model_calibrated
    assert not replace(good, model=replace(SCORES, model_log_loss_on_market=1.031)).model_close_to_market
    assert not replace(good, radar=Clv(n=200, mean=0.015, std_error=0.01)).radar_passes  # sotto i 2 errori standard
    assert not replace(good, radar=None).radar_passes


def test_sharp_opening_prefers_pinnacle():
    pin = {1: {"1X2": {"1": 0.5, "X": 0.3, "2": 0.2}}}
    bfx = {1: {"1X2": {"1": 0.4, "X": 0.3, "2": 0.3}}, 2: {"1X2": {"1": 0.6, "X": 0.2, "2": 0.2}}}
    merged = sharp_opening(pin, bfx)
    assert merged[1] == pin[1] and merged[2] == bfx[2]
