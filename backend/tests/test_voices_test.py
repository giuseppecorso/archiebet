"""Prova D174: regole sulle tre voci e doppie, con valori calcolati a mano."""

from datetime import UTC, datetime

import pytest

from app.forecast import study_backtest as bt
from app.forecast import voices_test as vt
from app.forecast.daily_replay import seal

WHEN = "2025-03-08T18:00:00+00:00"


def row(price: float = 2.5, sharp: float = 0.42, consensus: float = 0.41, study: float = 0.45, match_id: int = 1, when: str = WHEN, won: bool = True, clv: float | None = 0.01) -> dict:
    return {"match_id": match_id, "when": when, "market": "1X2", "selection": "1", "price": price, "sharp": sharp, "consensus": consensus, "study": study, "won": won, "clv": clv}


def test_three_voices_need_every_voice_above_the_price():
    assert vt.passes(row(), "tre_voci")  # 2,5 × 0,41 = 1,025: anche la più prudente è sopra
    assert not vt.passes(row(study=0.39), "tre_voci")  # lo studio dice no
    assert not vt.passes(row(consensus=0.39), "tre_voci")


def test_the_control_rule_is_pinnacle_yes_study_no():
    assert vt.passes(row(study=0.39), "contro")
    assert not vt.passes(row(), "contro")


def test_base_only_looks_at_pinnacle():
    assert vt.passes(row(consensus=0.3, study=0.3), "base")
    assert not vt.passes(row(sharp=0.39), "base")


def test_one_pick_per_match_the_best_according_to_pinnacle():
    better = row(price=2.6, sharp=0.42)
    assert vt.picks([row(), better], "base", "da 2") == [better]


def test_zones_cut_on_the_offered_price():
    assert vt.picks([row(price=1.9, sharp=0.6)], "base", "da 2") == []
    assert len(vt.picks([row(price=1.9, sharp=0.6)], "base", "da 1,40")) == 1
    assert vt.picks([row(price=6.0, sharp=0.2)], "base", "da 2") == []


def test_candidates_carry_no_result():
    book = {"pinnacle": {"1X2": {"1": 2.0, "X": 3.5, "2": 4.0}}, "market_avg": {"1X2": {"1": 1.95, "X": 3.4, "2": 3.9}}, "bet365": {"1X2": {"1": 2.1, "X": 3.3, "2": 3.8}}}
    study = {"id": 1, "when": WHEN, "pure": {"lam": 1.5, "mu": 1.0, "rho": -0.1}}
    found = vt.candidates([study], {1: book})
    assert len(found) == 3
    assert not {"won", "clv", "hg", "ag"} & set(found[0])


def test_a_match_without_pinnacle_is_left_out():
    book = {"market_avg": {"1X2": {"1": 1.95, "X": 3.4, "2": 3.9}}, "bet365": {"1X2": {"1": 2.1, "X": 3.3, "2": 3.8}}}
    assert vt.candidates([{"id": 1, "when": WHEN, "pure": {"lam": 1.5, "mu": 1.0, "rho": -0.1}}], {1: book}) == []


def test_opening_uses_results_and_refuses_a_broken_seal():
    sealed = [{k: v for k, v in row().items() if k not in ("won", "clv")}]
    game = bt.G(1, datetime(2025, 3, 8, 18, tzinfo=UTC), 135, 2024, 1, 2, 2, 0, 1, 0, None, None)
    closing = {1: {"pinnacle": {"1X2": {"1": 2.0, "X": 3.5, "2": 4.0}}}}
    [opened] = vt.open_candidates(sealed, seal(sealed), [game], closing)
    assert opened["won"] is True
    assert opened["clv"] > 0
    with pytest.raises(ValueError):
        vt.open_candidates(sealed, "impronta sbagliata", [game], closing)


def test_summary_counts_roi_and_clv():
    s = vt.summarize([row(price=2.0, sharp=0.5, won=True, clv=0.02), row(price=2.0, sharp=0.5, won=False, clv=None, match_id=2)])
    assert (s.n, s.won, s.expected, s.roi, s.clv_n) == (2, 1, 1.0, 0.0, 1)


def test_doubles_take_the_two_best_of_the_day():
    a, b, c = row(price=2.4, sharp=0.45, match_id=1), row(price=2.5, sharp=0.42, match_id=2), row(price=2.2, sharp=0.46, match_id=3)
    assert vt.doubles([a, b, c]) == [(a, b)]  # 8,0% e 5,0% battono l'1,2% della terza


def test_whelan_keeps_long_prices_apart():
    assert vt.doubles([row(price=4.0, sharp=0.28, match_id=1), row(price=4.5, sharp=0.25, match_id=2)]) == []


def test_pair_returns_compare_the_double_with_the_same_singles():
    together, apart = vt.pair_returns([(row(price=2.0, won=True), row(price=3.0, won=True)), (row(price=2.0, won=True), row(price=3.0, won=False))])
    assert together == [5.0, -1.0]
    assert apart == [1.5, 0.0]


def test_study_yes_needs_pinnacle_and_the_study():
    assert vt.passes(row(consensus=0.3), "studio_si")
    assert not vt.passes(row(study=0.39), "studio_si")


def many(rule_row: dict, n: int, year: int = 2015) -> list[dict]:
    return [{**rule_row, "match_id": i + year * 1000, "when": f"{year}-10-01T18:00:00+00:00"} for i in range(n)]


def test_the_verdict_applies_all_five_criteria():
    good = [{**r, "clv": 0.02 + (i % 2) * 0.01, "won": i % 2 == 0} for y in range(2012, 2023) for i, r in enumerate(many(row(study=0.45), 12, y))]
    rest = [{**r, "clv": 0.0, "won": False} for r in many(row(study=0.39), 12, 2030)]
    result = vt.verdict(good + rest, "studio_si")
    assert all(v for k, v in result["checks"].items()), result
    assert result["passed"] is True


def test_the_verdict_fails_with_too_few_picks():
    result = vt.verdict(many(row(), 5), "studio_si")
    assert result["checks"]["almeno 100 giocate"] is False
    assert result["passed"] is False


def test_the_archive_study_sees_only_earlier_games():
    from dataclasses import replace

    from tests.test_daily_replay import league

    games = league()
    before = vt.archive_studies(games, 2024, log=lambda _: None)
    cutoff = min(datetime.fromisoformat(s["when"]) for s in before)
    last = max(g.date for g in games)
    rewritten = [replace(g, hg=g.ag, ag=g.hg) if g.date == last else g for g in games]
    assert cutoff < last
    assert [s["pure"] for s in vt.archive_studies(rewritten, 2024, log=lambda _: None)] == [s["pure"] for s in before]  # il risultato dell'ultima giornata non può cambiare nulla
