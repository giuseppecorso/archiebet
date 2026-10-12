"""Banco di prova contro il mercato e fattori: formule controllate, casi costruiti a mano."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from scipy.optimize import check_grad

from app.forecast.data import Game
from app.forecast.factors import nothing_to_play_for, rest_difference
from app.forecast.market_model import MarketRow, _design, _nll, fit, predict, walk_forward_by_season

T0 = datetime(2023, 8, 20, 18, tzinfo=UTC)


def test_neutral_parameters_return_the_market():
    p = np.array([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
    theta = np.zeros(5)
    theta[0] = 1.0
    assert predict(theta, p, np.zeros((2, 1))) == pytest.approx(p)


def test_gradient_matches_numerical_derivative():
    rng = np.random.default_rng(0)
    p = rng.dirichlet([4, 3, 3], 40)
    x = rng.normal(size=(40, 2))
    y = rng.integers(0, 3, 40)
    design = _design(p, x)
    theta0 = rng.normal(0, 0.3, design.shape[0])
    assert check_grad(lambda t: _nll(t, design, y)[0], lambda t: _nll(t, design, y)[1], theta0) < 1e-5


def test_fit_learns_a_factor_the_market_ignores():
    """Mercato sempre 1/3 ciascuno, ma quando il fattore vale +1 vince quasi sempre la casa."""
    rng = np.random.default_rng(1)
    n = 3000
    x = rng.choice([-1.0, 0.0, 1.0], n)
    y = np.array([0 if (v > 0 and rng.random() < 0.7) else rng.integers(0, 3) for v in x])
    p = np.full((n, 3), 1 / 3)
    theta = fit(p, x.reshape(-1, 1), y)
    boosted = predict(theta, p[:1], np.array([[1.0]]))[0]
    assert boosted[0] > 0.6  # vera probabilità ≈ 0,7 + 0,3/3 = 0,8 (con un po' di prudenza dal termine L2)


def test_walk_forward_uses_only_earlier_seasons():
    rows = [MarketRow(i, "2022/23", 0, (0.5, 0.3, 0.2)) for i in range(50)]
    rows += [MarketRow(100 + i, "2023/24", 2, (0.5, 0.3, 0.2)) for i in range(50)]
    preds = walk_forward_by_season(rows, {}, ["2022/23", "2023/24"], n_features=1)
    assert set(preds) == {100 + i for i in range(50)}  # la prima stagione non ha passato: niente previsioni
    # Nel passato vinceva sempre la casa: la correzione la favorisce, anche se nel 2023/24 vince l'ospite
    assert preds[100][0] > 0.5


def _game(mid, day, home, away, hg=1, ag=0, season="2023/24", tier=1, comp=1):
    return Game(mid, comp, T0 + timedelta(days=day), season, tier, home, away, hg, ag)


def test_rest_difference_by_hand():
    games = [_game(1, 0, 1, 2), _game(2, 3, 3, 4), _game(3, 7, 1, 3), _game(4, 20, 2, 4)]
    rest = rest_difference(games)
    assert rest[1] == 0  # prima partita di entrambe: riposo pieno
    assert rest[3] == pytest.approx(7 - 4)  # squadra 1 riposa 7 giorni, squadra 3 solo 4
    assert rest[4] == pytest.approx(0)  # entrambe oltre 8 giorni: tagliati a 8


def test_nothing_to_play_for_at_the_end_of_the_season():
    """4 squadre (6 giornate), retrocede l'ultima, obiettivo il primo posto: la 2 a fine stagione è "in vacanza"."""
    from app.forecast import factors

    factors.RULES[9] = factors.SeasonRules(relegation=1, target=1)
    try:
        g = lambda mid, day, h, a, hg, ag: _game(mid, day, h, a, hg, ag, tier=9)  # noqa: E731
        games = [
            g(1, 0, 1, 2, 2, 0), g(2, 0, 3, 4, 1, 0),  # 1: 3pt, 2: 0, 3: 3, 4: 0
            g(3, 7, 1, 3, 1, 0), g(4, 7, 2, 4, 3, 0),  # 1: 6, 2: 3, 3: 3, 4: 0
            g(5, 14, 1, 4, 2, 0), g(6, 14, 2, 3, 2, 0),  # 1: 9, 2: 6, 3: 3, 4: 0
            g(7, 21, 2, 1, 0, 0), g(8, 21, 4, 3, 0, 0),  # prima di questa giornata la 2 ha 6 punti
        ]
        flags = nothing_to_play_for(games)
        # Prima della 4a giornata (2 partite a testa da giocare): la 4 (ultima) ha 0 punti e può fare al massimo 6,
        # la 2 ne ha 6 → non ancora salva. Il primo posto (9) è ancora raggiungibile: 6 + 6 = 12. Nessuna in vacanza.
        assert flags[7] == 0 and flags[1] == 0
    finally:
        del factors.RULES[9]


def test_safe_and_out_of_reach_flag():
    """4 squadre, 6 giornate. Prima dell'ultima: 1 → 15 punti, 2 → 9, 3 → 6, 4 → 0 (una partita a testa)."""
    from app.forecast import factors

    factors.RULES[9] = factors.SeasonRules(relegation=1, target=1)
    try:
        g = lambda mid, day, h, a, hg, ag: _game(mid, day, h, a, hg, ag, tier=9)  # noqa: E731
        games = [
            g(1, 0, 1, 2, 1, 0), g(2, 0, 3, 4, 1, 0),
            g(3, 7, 1, 3, 1, 0), g(4, 7, 2, 4, 1, 0),
            g(5, 14, 1, 4, 1, 0), g(6, 14, 2, 3, 1, 0),
            g(7, 21, 2, 1, 0, 1), g(8, 21, 4, 3, 0, 1),
            g(9, 28, 3, 1, 0, 1), g(10, 28, 4, 2, 0, 1),
            g(11, 35, 2, 4, 0, 0), g(12, 35, 3, 1, 0, 0),  # ultima giornata
        ]
        flags = nothing_to_play_for(games)
        # La 4 può arrivare al massimo a 3 punti: 2 (9) e 3 (6) sono salve. Il primo posto (15) è irraggiungibile
        # per entrambe (9+3, 6+3): sono "in vacanza". La 1 ha un obiettivo, la 4 lotta per salvarsi.
        assert flags[11] == 1.0  # 2 in vacanza, 4 no
        assert flags[12] == 1.0  # 3 in vacanza, 1 no
        assert flags[9] == 0.0  # alla 5a giornata la 3 (3 punti) non è ancora salva
    finally:
        del factors.RULES[9]


def test_factor_test_clv_by_hand():
    from app.forecast.factor_test import _clv

    probs = {1: np.array([0.5, 0.3, 0.2])}
    offered = {1: {"1X2": {"1": 2.1, "X": 3.2, "2": 4.5}}}  # valore: 1 → +5%, X → −4%, 2 → −10%
    closing = {1: {"1X2": {"1": 0.49, "X": 0.30, "2": 0.21}}}
    clv = _clv(probs, offered, closing, threshold=0.02)
    assert clv.n == 1 and clv.mean == pytest.approx(2.1 * 0.49 - 1)
    assert _clv(probs, offered, closing, threshold=0.06) is None


def test_factor_test_detects_a_useful_factor(tmp_path):
    """Un fattore costruito apposta (che il mercato ignora) deve passare; uno casuale no."""
    from app.forecast.factor_test import run

    rng = np.random.default_rng(3)
    rows, useful, noise = [], {}, {}
    for i in range(4000):
        x = rng.choice([-1.0, 1.0])
        p_home = 0.45 + 0.15 * x  # verità
        y = 0 if rng.random() < p_home else (1 if rng.random() < 0.5 else 2)
        rows.append(MarketRow(i, "2022/23" if i < 2000 else "2023/24", y, (0.45, 0.275, 0.275)))
        useful[i], noise[i] = [x], [rng.normal()]
    results = {r.name: r for r in run(rows, {"utile": useful, "rumore": noise}, ["2023/24"], {}, {}, {}, vault_marker=tmp_path / "x")}
    assert results["utile"].passes
    assert not results["rumore"].passes
    assert results["Mercato ricalibrato"].vs_baseline is None
