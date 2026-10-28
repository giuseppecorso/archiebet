import math
from datetime import UTC, datetime, timedelta

import pytest

from app.forecast.player_weight import (
    SHRINK_GAMES,
    Appearance,
    PlayerBook,
    RoleMeans,
    goals_factor,
    lineup_change,
    parse_appearances,
    role_means,
)

T0 = datetime(2025, 1, 1, tzinfo=UTC)
MEANS = RoleMeans({"G": 0.0, "D": 1.0, "M": 2.0, "F": 3.0}, {"G": 6.8, "D": 6.8, "M": 6.8, "F": 6.8})


def app(fid, day, player, minutes=90, shots=0, kp=0, rating=6.8, position="M", started=True, team=1):
    return Appearance(fid, T0 + timedelta(days=day), team, player, f"P{player}", position, minutes, started, shots, kp, rating)


def season(n_games, star_shots=6):
    """Squadra con 11 titolari fissi: il giocatore 11 è un attaccante che tira molto, il 12 una riserva che tira poco."""
    out = []
    for g in range(n_games):
        for p in range(1, 12):
            shots = star_shots if p == 11 else 1
            out.append(app(g, g * 7, p, shots=shots, position="F" if p == 11 else "M", rating=7.5 if p == 11 else 6.8))
        out.append(app(g, g * 7, 12, minutes=0, started=False, position="F", rating=None))
    return out


def test_parse_marks_starters_and_skips_ratings_of_short_cameos():
    body = {"response": [{"team": {"id": 5}, "players": [
        {"player": {"id": i, "name": f"N{i}"}, "statistics": [{"games": {"minutes": 90, "position": "D", "rating": "7.1", "substitute": False},
                                                                 "shots": {"total": None}, "passes": {"key": 2}}]} for i in range(11)
    ] + [
        {"player": {"id": 99, "name": "Sub"}, "statistics": [{"games": {"minutes": 8, "position": "F", "rating": "6.5", "substitute": True},
                                                              "shots": {"total": 1}, "passes": {"key": None}}]},
    ]}]}  # fmt: skip
    rows = parse_appearances(body, 1, T0)
    assert sum(r.started for r in rows) == 11
    sub = next(r for r in rows if r.player == 99)
    assert not sub.started and sub.rating is None and sub.shots == 1
    assert rows[0].shots == 0 and rows[0].key_passes == 2 and rows[0].rating == pytest.approx(7.1)


def test_parse_falls_back_to_most_minutes_when_substitutes_are_not_marked():
    players = [{"player": {"id": i}, "statistics": [{"games": {"minutes": 90 - i, "substitute": False}}]} for i in range(14)]
    rows = parse_appearances({"response": [{"team": {"id": 1}, "players": players}]}, 1, T0)
    assert {r.player for r in rows if r.started} == set(range(11))


def test_weighted_shrinks_towards_role_mean_and_ignores_the_future():
    book = PlayerBook([app(1, 0, 7, shots=10, position="F"), app(2, 30, 7, shots=50, position="F")])
    w = book.weighted(7, T0 + timedelta(days=10), MEANS)  # vede solo la prima partita
    assert w.attack == pytest.approx((10 + SHRINK_GAMES * 3.0) / (1 + SHRINK_GAMES))
    nobody = book.weighted(42, T0, MEANS, "D")
    assert nobody.attack == pytest.approx(1.0) and nobody.rating == pytest.approx(6.8)


def test_same_eleven_means_no_change():
    book = PlayerBook(season(8))
    kickoff = T0 + timedelta(days=8 * 7)
    change = lineup_change(book, 1, [(p, None) for p in range(1, 12)], kickoff, MEANS)
    assert change.attack == pytest.approx(0.0) and change.quality == pytest.approx(0.0)
    assert change.missing == () and change.replacing == ()


def test_missing_shooter_replaced_by_weaker_reserve_lowers_attack_and_quality():
    book = PlayerBook(season(8))
    kickoff = T0 + timedelta(days=8 * 7)
    change = lineup_change(book, 1, [(p, None) for p in range(1, 11)] + [(12, "F")], kickoff, MEANS)
    assert change.attack < 0 and change.quality < 0
    assert [w.player for w in change.missing] == [11] and [w.player for w in change.replacing] == [12]
    # la riserva senza minuti vale la media del ruolo (attaccante: 3 a partita), non zero
    assert change.replacing[0].attack == pytest.approx(3.0)


def test_unknown_when_team_has_too_few_games():
    book = PlayerBook(season(3))
    assert lineup_change(book, 1, [(p, None) for p in range(1, 12)], T0 + timedelta(days=30), MEANS) is None


def test_role_means_and_goals_factor():
    means = role_means([app(1, 0, 1, shots=4, position="F", rating=7.0), app(1, 0, 2, minutes=45, kp=1, position="D", rating=None)])
    assert means.attack["F"] == pytest.approx(4.0) and means.attack["D"] == pytest.approx(2.0)
    assert means.rating["F"] == pytest.approx(7.0)
    assert goals_factor(-0.1, 0.0, 0.0, 1.0, 0.0, 0.0) == pytest.approx(math.exp(-0.1))
    assert goals_factor(0.0, 0.2, 0.1, 0.0, 0.5, 0.3) == pytest.approx(math.exp(0.1 - 0.03))
