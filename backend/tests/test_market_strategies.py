from datetime import date

import pytest

from app.forecast import market_strategies as ms


def game(mid=1, hg=1, ag=0, season="2015/16", day=date(2016, 1, 10), moment=None, b365=None, close=None, avg=None, best=None, fo=None, fc=None):
    b365 = b365 or {"1X2": {"1": 2.0, "X": 3.4, "2": 4.0}, "OU2.5": {"over": 1.9, "under": 1.95}}
    fair = {"1X2": {"1": 0.48, "X": 0.28, "2": 0.24}, "OU2.5": {"over": 0.5, "under": 0.5}}
    return ms.Game(mid, season, "ITA-A", day, moment, hg, ag, b365, close or {}, avg or {}, best or {}, fo or fair, fc or fair)


def test_won_for_each_market():
    g = game(hg=2, ag=2)
    assert ms.won(g, "1X2", "X") and not ms.won(g, "1X2", "1")
    assert ms.won(g, "OU2.5", "over") and not ms.won(g, "OU2.5", "under")


def test_profit_and_clv_of_a_single():
    b = ms.single(game(), "1X2", "1", 2.0)
    assert b.won and b.profit == pytest.approx(1.0)
    assert b.clv == pytest.approx(2.0 * 0.48 - 1)  # quota × probabilità giusta di chiusura − 1
    lost = ms.single(game(hg=0, ag=1), "1X2", "1", 2.0)
    assert lost.profit == -1.0


def test_always_and_price_band():
    games = [game(1), game(2, b365={"1X2": {"1": 1.4, "X": 4.5, "2": 7.0}})]
    assert len(ms.always("1X2", "X")(games)) == 2
    assert [b.price for b in ms.price_band(1.0, 1.5)(games)] == [1.4]
    assert [b.price for b in ms.price_band(5.0, 1000)(games)] == [7.0]


def test_even_draws_only_between_equal_teams():
    even = game(1, b365={"1X2": {"1": 2.6, "X": 3.1, "2": 2.9}})
    uneven = game(2, b365={"1X2": {"1": 1.8, "X": 3.6, "2": 4.5}})
    assert [b.cluster for b in ms.even_draws([even, uneven])] == [1]


def test_late_draws_only_at_the_end_of_the_season():
    assert [b.cluster for b in ms.late_draws([game(1, moment=ms.LATE), game(2, moment=None)])] == [1]


def test_favourites_treble_takes_the_three_lowest_of_the_day():
    d = date(2016, 1, 10)
    prices = [1.30, 1.50, 1.20, 1.70, 1.45]
    games = [game(i, day=d, b365={"1X2": {"1": p, "X": 4.0, "2": 8.0}}) for i, p in enumerate(prices, 1)]
    games.append(game(9, day=date(2016, 1, 11), b365={"1X2": {"1": 1.2, "X": 5.0, "2": 9.0}}))  # da sola nel suo giorno: niente multipla
    [bet] = ms.favourites_treble(games)
    assert bet.price == pytest.approx(1.20 * 1.30 * 1.45)
    assert bet.won  # tutte finite 1-0
    assert bet.cluster == d.toordinal()
    games[0] = game(1, day=d, hg=0, ag=0, b365={"1X2": {"1": 1.30, "X": 4.0, "2": 8.0}})
    assert not ms.favourites_treble(games)[0].won


def test_follow_move_plays_at_bet365_closing():
    fo = {"1X2": {"1": 0.40, "X": 0.30, "2": 0.30}}
    fc = {"1X2": {"1": 0.46, "X": 0.28, "2": 0.26}}
    close = {"1X2": {"1": 2.05, "X": 3.4, "2": 3.6}}
    [bet] = ms.follow_move([game(fo=fo, fc=fc, close=close)])
    assert bet.price == 2.05
    assert ms.follow_move([game(fo=fo, fc=fc)]) == []  # senza bet365 di chiusura non si gioca
    small = {"1X2": {"1": 0.42, "X": 0.29, "2": 0.29}}
    assert ms.follow_move([game(fo=fo, fc=small, close=close)]) == []


def test_value_bets_follow_the_d72_rule():
    # giusto 0.48 a quota 2.30: valore 0.104, sopra la soglia D72 (2% × √1,3 ≈ 0,023)
    g = game(b365={"1X2": {"1": 2.30, "X": 3.4, "2": 4.0}})
    assert [(b.price) for b in ms.value_bets([g])] == [2.30]
    assert ms.value_bets([game()]) == []  # 0.48 × 2.0 − 1 < 0


def test_consensus_rule_of_kaunitz():
    # media 2.0 → 1/2 − 0.05 = 0.45 → serve una quota massima oltre 2.222
    g = game(avg={"1X2": {"1": 2.0}}, best={"1X2": {"1": 2.30}})
    assert [b.price for b in ms.consensus([g])] == [2.30]
    assert ms.consensus([game(avg={"1X2": {"1": 2.0}}, best={"1X2": {"1": 2.20}})]) == []


def test_pass_needs_positive_tuning_and_significant_confirmation():
    good = ms.part([ms.Bet(i, "2021/22", 3.0, i % 2 == 0, 0.0) for i in range(400)])
    assert good.roi.mean == pytest.approx(0.5)  # metà vinte a quota 3: torna 1,5 per ogni euro
    assert good.hit_rate == pytest.approx(0.5) and good.avg_price == pytest.approx(3.0)
    assert ms.passed(good, good)
    bad = ms.part([ms.Bet(i, "2014/15", 2.0, i % 3 == 0, 0.0) for i in range(300)])
    assert bad.roi.mean < 0
    assert not ms.passed(bad, good)
    assert not ms.passed(good, ms.part([]))


def test_beats_close_is_about_clv_only():
    sharp = ms.part([ms.Bet(i, "2015/16", 2.0, False, 0.03 + 0.01 * (i % 3)) for i in range(200)])
    assert sharp.roi.mean == -1.0
    assert ms.beats_close(sharp, sharp)
    assert not ms.passed(sharp, sharp)  # il verdetto resta sul rendimento
    flat = ms.part([ms.Bet(i, "2015/16", 2.0, False, 0.01 * (i % 3) - 0.01) for i in range(200)])
    assert not ms.beats_close(sharp, flat)


def test_evaluate_splits_tuning_and_confirmation():
    games = [game(i, season="2015/16") for i in range(5)] + [game(10 + i, season="2022/23") for i in range(3)] + [game(99, season="2025/26")]
    rows = {r["key"]: r for r in ms.evaluate(games)}
    assert rows["home"]["tuning"]["n"] == 5
    assert rows["home"]["confirm"]["n"] == 3  # la 2025/26 non si tocca
    assert len(rows) == len(ms.STRATEGIES)
