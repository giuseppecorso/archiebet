"""Backtest walk-forward: niente dati dal futuro, cassaforte rispettata, conteggi corretti."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.forecast.backtest import ModelConfig, Prediction, compare, score, walk_forward
from app.forecast.data import Game
from app.forecast.vault import VaultLockedError

T0 = datetime(2022, 8, 20, 18, 0, tzinfo=UTC)


def _league(seasons, teams=6, seed=0):
    """Campionati finti: ogni settimana tutte le squadre giocano, girone di andata e ritorno."""
    rng = np.random.default_rng(seed)
    strength = np.linspace(0.4, -0.4, teams)
    games, week, mid = [], 0, 1
    for season in seasons:
        for h in range(teams):
            for a in range(teams):
                if h != a:
                    hg = int(rng.poisson(np.exp(0.25 + strength[h] - strength[a] / 2)))
                    ag = int(rng.poisson(np.exp(strength[a] - strength[h] / 2)))
                    games.append(Game(mid, 1, T0 + timedelta(days=7 * week), season, 1, h, a, hg, ag))
                    mid += 1
                    week += mid % 3 == 0  # tre partite a settimana
    return games


FAST = ModelConfig(refit_every_days=28, elo_prior=False)


def test_predicts_only_the_requested_seasons(tmp_path):
    games = _league(["2022/23", "2023/24"])
    res = walk_forward(games, ["2023/24"], FAST, vault_marker=tmp_path / "x")
    assert len(res.predictions) + res.skipped == 30
    assert res.skipped == 0
    assert {p.season for p in res.predictions} == {"2023/24"}
    for p in res.predictions:
        assert sum(p.p_1x2) == pytest.approx(1.0)


def test_future_results_do_not_change_predictions(tmp_path):
    games = _league(["2022/23", "2023/24"])
    base = walk_forward(games, ["2023/24"], FAST, vault_marker=tmp_path / "x").predictions[0]
    target = next(g for g in games if g.match_id == base.match_id)
    day = target.kickoff_at.replace(hour=0, minute=0)
    # Riscrivo tutti i risultati dal giorno della partita in poi (compresa lei): la previsione non deve cambiare
    altered = [replace(g, home_goals=0, away_goals=7) if g.kickoff_at >= day else g for g in games]
    again = walk_forward(altered, ["2023/24"], FAST, vault_marker=tmp_path / "x").predictions[0]
    assert again.p_1x2 == pytest.approx(base.p_1x2, abs=1e-9)


def test_team_without_history_is_skipped(tmp_path):
    games = _league(["2022/23"])
    newcomer = Game(9999, 1, games[-1].kickoff_at + timedelta(days=30), "2023/24", 1, 0, 77, 1, 0)
    res = walk_forward(games + [newcomer], ["2023/24"], FAST, vault_marker=tmp_path / "x")
    assert res.predictions == [] and res.skipped == 1


def test_vault_seasons_cannot_be_evaluated(tmp_path):
    with pytest.raises(VaultLockedError):
        walk_forward(_league(["2024/25", "2025/26"]), ["2025/26"], FAST, vault_marker=tmp_path / "missing")


def test_score_compares_with_market_on_common_matches(tmp_path):
    preds = walk_forward(_league(["2022/23", "2023/24"]), ["2023/24"], FAST, vault_marker=tmp_path / "x").predictions
    market = {preds[0].match_id: (1 / 3, 1 / 3, 1 / 3)}
    s = score(preds, market)
    assert s.n == 30 and s.n_market == 1
    assert s.market_log_loss == pytest.approx(np.log(3))
    assert 0 < s.rps < s.brier < 2


def test_elo_prior_predicts_teams_without_history(tmp_path):
    games = _league(["2022/23"])
    newcomer = Game(9999, 1, games[-1].kickoff_at + timedelta(days=30), "2023/24", 1, 0, 77, 1, 0)
    res = walk_forward(games + [newcomer], ["2023/24"], replace(FAST, elo_prior=True), vault_marker=tmp_path / "x")
    assert res.skipped == 0 and len(res.predictions) == 1


def test_elo_prior_does_not_look_ahead(tmp_path):
    games = _league(["2022/23", "2023/24"])
    cfg = replace(FAST, elo_prior=True)
    base = walk_forward(games, ["2023/24"], cfg, vault_marker=tmp_path / "x").predictions[0]
    day = next(g for g in games if g.match_id == base.match_id).kickoff_at.replace(hour=0, minute=0)
    altered = [replace(g, home_goals=0, away_goals=7) if g.kickoff_at >= day else g for g in games]
    again = walk_forward(altered, ["2023/24"], cfg, vault_marker=tmp_path / "x").predictions[0]
    assert again.p_1x2 == pytest.approx(base.p_1x2, abs=1e-9)


def _pred(match_id, p_home, outcome=0):
    rest = (1 - p_home) / 2
    return Prediction(match_id, 1, "2023/24", outcome, 2, True, (p_home, rest, rest), 0.5, 0.5)


def test_compare_by_hand():
    a = [_pred(1, 0.5), _pred(2, 0.5), _pred(3, 0.5)]
    b = [_pred(1, 0.6), _pred(2, 0.4), _pred(4, 0.9)]  # la 3 manca in B, la 4 in A: si confrontano solo 1 e 2
    c = compare(a, b)
    d1, d2 = -np.log(0.6) + np.log(0.5), -np.log(0.4) + np.log(0.5)
    assert c.n == 2
    assert c.mean_diff == pytest.approx((d1 + d2) / 2)
    assert c.std_error == pytest.approx(np.std([d1, d2], ddof=1) / np.sqrt(2))


def test_compare_requires_a_clear_improvement():
    a = [_pred(i, 0.5) for i in range(50)]
    assert compare(a, [_pred(i, 0.6) for i in range(50)]).b_is_better  # sempre meglio: promossa
    noisy = [_pred(i, 0.6 if i % 2 else 0.41) for i in range(50)]  # un po' meglio, un po' peggio
    assert not compare(a, noisy).b_is_better
