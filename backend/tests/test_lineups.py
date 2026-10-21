"""Formazioni previste (D123)."""

from datetime import UTC, datetime, timedelta

from app.forecast import lineups as lu
from app.forecast.player_props import PlayerGame

START = datetime(2025, 8, 20, tzinfo=UTC)


def _game(fixture: int, day: int, players: list[tuple[int, str, bool]], team: int = 1) -> list[PlayerGame]:
    """players: (id, ruolo, titolare)"""
    return [PlayerGame(fixture, 135, 2025, START + timedelta(days=day), team, 2, True, pid, f"P{pid}", pos, 90 if st else 20, 0, 0, not st)
            for pid, pos, st in players]  # fmt: skip


def _squad(rotate: int = 0) -> list[tuple[int, str, bool]]:
    keeper = [(1, "G", True), (99, "G", False)]
    outfield = [(i, "M", True) for i in range(2, 12)]
    if rotate:
        outfield[-1] = (11, "M", False)
        outfield.append((rotate, "F", True))
    return keeper + outfield


def test_probable_lineup_weights_recent_games():
    games = _game(1, 0, _squad()) + _game(2, 7, _squad(rotate=12))
    lineup = lu.weighted_lineup(games, 1, START + timedelta(days=14))
    p = {x.player: x.p_start for x in lineup.eleven + lineup.doubtful}
    assert len(lineup.eleven) == 11 and lineup.eleven[0].player == 1
    assert p[12] == 5 / 9 and p[11] == 4 / 9  # la partita più recente pesa 5, quella prima 4
    assert 12 in {x.player for x in lineup.eleven} and 11 in {x.player for x in lineup.doubtful}
    assert 99 not in p  # il secondo portiere non è mai partito titolare


def test_absent_players_are_left_out():
    games = _game(1, 0, _squad())
    lineup = lu.weighted_lineup(games, 1, START + timedelta(days=7), absent={5})
    assert 5 not in {x.player for x in lineup.eleven} and len(lineup.eleven) == 10


def test_no_future_data():
    games = _game(1, 0, _squad()) + _game(2, 7, _squad(rotate=12))
    lineup = lu.weighted_lineup(games, 1, START + timedelta(days=3))
    assert 12 not in {x.player for x in lineup.eleven + lineup.doubtful}
    assert lu.weighted_lineup(games, 1, START) is None


def test_backtest_counts_hits():
    games = []
    for k in range(7):
        games += _game(k, 7 * k, _squad(rotate=12 if k == 4 else 0))  # turnover una volta sola, alla partita 4
    t = lu.backtest(games)
    assert t is not None and t.n == 2  # partite 5 e 6: le prime con 5 precedenti
    assert t.last == 10.5  # dopo il turnover l'ultima formazione sbaglia un giocatore
    assert t.archie == 11  # il metodo pesato non si fa ingannare da una partita sola


def test_predicted_lineup_uses_last_xi_minus_absent():
    games = _game(1, 0, _squad()) + _game(2, 7, _squad()) + _game(3, 14, _squad(rotate=12))
    pred = lu.predicted_lineup(games, 1, START + timedelta(days=21))
    assert {p.player for p in pred.eleven} == {1, *range(2, 11), 12}  # l'ultima formazione, con il 12
    assert pred.eleven[0].position == "G" and 11 in {p.player for p in pred.doubtful}
    # il 12 è assente secondo le notizie: al suo posto il più presente di recente (l'11)
    pred = lu.predicted_lineup(games, 1, START + timedelta(days=21), absent={12})
    assert {p.player for p in pred.eleven} == {1, *range(2, 12)}


def test_predicted_lineup_replaces_absent_keeper_with_keeper():
    games = _game(1, 0, [(99, "G", True)] + _squad()[2:]) + _game(2, 7, _squad())
    pred = lu.predicted_lineup(games, 1, START + timedelta(days=14), absent={1})
    assert [p.player for p in pred.eleven if p.position == "G"] == [99] and len(pred.eleven) == 11


def test_starters_without_substitute_flag():
    rows = [PlayerGame(1, 135, 2026, START, 1, 2, True, pid, f"P{pid}", "M", minutes, 0, 0) for pid, minutes in
            [(i, 90) for i in range(1, 10)] + [(10, 63), (11, 70), (12, 27), (13, 20), (14, 0)]]  # fmt: skip
    assert lu.starters(rows) == set(range(1, 12))
