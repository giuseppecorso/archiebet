"""Modello Dixon-Coles: formule a mano, gradiente controllato numericamente, parametri noti ritrovati."""

from datetime import datetime, timedelta

import numpy as np
import pytest
from scipy.optimize import check_grad
from scipy.stats import poisson

from app.forecast.dixon_coles import _objective, fit_dixon_coles, score_matrix, tau, time_decay_weights


def test_tau_low_scores_by_hand():
    lam, mu, rho = 1.5, 1.2, -0.1
    hg = np.array([0, 0, 1, 1, 2, 0])
    ag = np.array([0, 1, 0, 1, 1, 3])
    expected = [1 - 1.5 * 1.2 * -0.1, 1 + 1.5 * -0.1, 1 + 1.2 * -0.1, 1 + 0.1, 1, 1]
    assert tau(hg, ag, lam, mu, rho) == pytest.approx(expected)


def test_score_matrix_without_rho_is_independent_poisson():
    m = score_matrix(1.4, 1.1, 0.0)
    assert m.sum() == pytest.approx(1.0)
    assert m[2, 1] == pytest.approx(poisson.pmf(2, 1.4) * poisson.pmf(1, 1.1), rel=1e-6)


def test_negative_rho_adds_draws_at_low_scores():
    plain, dc = score_matrix(1.3, 1.0, 0.0), score_matrix(1.3, 1.0, -0.1)
    assert dc.sum() == pytest.approx(1.0)
    assert dc[0, 0] > plain[0, 0] and dc[1, 1] > plain[1, 1]
    assert dc[1, 0] < plain[1, 0] and dc[0, 1] < plain[0, 1]


def test_time_decay_weights():
    ref = datetime(2025, 1, 31)
    w = time_decay_weights([ref, ref - timedelta(days=100)], ref, xi_per_day=0.005)
    assert w == pytest.approx([1.0, np.exp(-0.5)])


def test_time_decay_rejects_future_matches():
    ref = datetime(2025, 1, 31)
    with pytest.raises(ValueError, match="futuro"):
        time_decay_weights([ref + timedelta(days=1)], ref, xi_per_day=0.005)


def test_gradient_matches_numerical_derivative():
    rng = np.random.default_rng(1)
    n, k = 4, 60
    hi, ai = rng.integers(0, n, k), rng.integers(0, n, k)
    hg, ag = rng.poisson(1.4, k).astype(float), rng.poisson(1.1, k).astype(float)
    w = rng.uniform(0.2, 1.0, k)
    z = rng.normal(0, 1, n)
    x0 = np.concatenate([rng.normal(0, 0.2, 2 * n), [0.3, -0.08, 0.1]])
    err = check_grad(
        lambda p: _objective(p, n, hi, ai, hg, ag, w, 2.0, z)[0],
        lambda p: _objective(p, n, hi, ai, hg, ag, w, 2.0, z)[1],
        x0,
    )
    assert err < 1e-5


def _simulate(att, dfc, home_adv, rounds, rng):
    """Campionati simulati con parametri noti (a rho = 0): ogni squadra gioca con tutte, casa e fuori."""
    home, away, hg, ag = [], [], [], []
    n = len(att)
    for _ in range(rounds):
        for h in range(n):
            for a in range(n):
                if h != a:
                    home.append(h)
                    away.append(a)
                    hg.append(rng.poisson(np.exp(home_adv + att[h] - dfc[a])))
                    ag.append(rng.poisson(np.exp(att[a] - dfc[h])))
    return home, away, hg, ag


def test_fit_recovers_known_parameters():
    rng = np.random.default_rng(42)
    att = np.array([0.4, 0.2, 0.0, -0.1, -0.2, -0.3])
    dfc = np.array([0.3, 0.1, 0.0, 0.0, -0.1, -0.3])
    fit = fit_dixon_coles(*_simulate(att, dfc, 0.25, 120, rng))

    assert fit.converged
    assert fit.n_matches == 120 * 30
    assert fit.attack.sum() == pytest.approx(0.0, abs=1e-9)
    # Confronto a meno della costante comune (solo le differenze tra squadre contano)
    assert fit.attack - fit.attack.mean() == pytest.approx(att - att.mean(), abs=0.08)
    assert fit.defence - fit.defence.mean() == pytest.approx(dfc - dfc.mean(), abs=0.08)
    assert fit.home_advantage == pytest.approx(0.25, abs=0.05)
    assert fit.rho == pytest.approx(0.0, abs=0.06)


def test_expected_goals_follow_the_formula():
    rng = np.random.default_rng(7)
    fit = fit_dixon_coles(*_simulate(np.array([0.3, 0.0, -0.3]), np.zeros(3), 0.2, 30, rng))
    lam, mu = fit.expected_goals(0, 2)
    assert lam == pytest.approx(np.exp(fit.home_advantage + fit.attack[0] - fit.defence[2]))
    assert mu == pytest.approx(np.exp(fit.attack[2] - fit.defence[0]))
    assert fit.score_matrix(0, 2).sum() == pytest.approx(1.0)
    assert fit.has_team(0) and not fit.has_team(99)


def test_zero_weight_matches_are_ignored():
    rng = np.random.default_rng(3)
    home, away, hg, ag = _simulate(np.array([0.3, 0.0, -0.3]), np.zeros(3), 0.2, 20, rng)
    base = fit_dixon_coles(home, away, hg, ag)
    # Aggiungo partite assurde con peso zero: il risultato non deve cambiare
    noisy = fit_dixon_coles(home + [0] * 5, away + [2] * 5, hg + [0] * 5, ag + [9] * 5, weights=[1.0] * len(hg) + [0.0] * 5)
    assert noisy.attack == pytest.approx(base.attack, abs=1e-4)
    assert noisy.n_matches == base.n_matches


def test_ridge_shrinks_ratings_towards_average():
    rng = np.random.default_rng(5)
    data = _simulate(np.array([0.5, 0.0, -0.5]), np.zeros(3), 0.2, 3, rng)
    free, shrunk = fit_dixon_coles(*data), fit_dixon_coles(*data, ridge=0.5)
    assert np.abs(shrunk.attack).sum() < np.abs(free.attack).sum()


def test_no_matches_is_an_error():
    with pytest.raises(ValueError):
        fit_dixon_coles([], [], [], [])


def test_external_strength_sets_the_starting_point():
    """Con la forza esterna, una squadra senza partite riceve pendenza × forza (non più la media)."""
    rng = np.random.default_rng(11)
    att = np.array([0.4, 0.2, 0.0, -0.2, -0.4])
    home, away, hg, ag = _simulate(att, att, 0.25, 10, rng)
    strength = {i: float(att[i]) * 5 for i in range(5)} | {99: -3.0}  # la nuova squadra è debole
    fit = fit_dixon_coles(home, away, hg, ag, ridge=5.0, strength=strength, extra_teams=[99])
    assert fit.prior_slope > 0
    lam_vs_new, _ = fit.expected_goals(0, 99)
    lam_vs_mid, _ = fit.expected_goals(0, 2)
    assert lam_vs_new > lam_vs_mid  # contro la squadra debole si segna di più
    plain = fit_dixon_coles(home, away, hg, ag, ridge=5.0, extra_teams=[99])
    i = plain.teams.index(99)
    assert plain.attack[i] == pytest.approx(plain.defence[i], abs=1e-3)  # senza forza: squadra "neutra"
