"""Macchina del tempo (D171): la prova più importante è che i risultati futuri non possano entrare."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.forecast import daily_replay as dr
from app.forecast import study_backtest as bt
from app.forecast.daily import KINDS

MONDAY = datetime(2025, 3, 3, tzinfo=UTC)


def league(seed: int = 7) -> list[bt.G]:
    """Un campionato inventato di 3 stagioni: 12 squadre, andata e ritorno, con 15 giorni tra una giornata e l'altra."""
    rng = random.Random(seed)
    games, when, gid = [], datetime(2022, 8, 6, 18, tzinfo=UTC), 0
    strength = {t: rng.uniform(0.8, 1.8) for t in range(12)}
    for season in (2022, 2023, 2024):
        for _ in range(2):
            for offset in range(1, 12):
                teams = list(range(12))
                for i in range(6):
                    home, away = teams[i], teams[(i + offset) % 12]
                    hg, ag = min(rng.randrange(5), round(strength[home] * rng.random() * 3)), min(rng.randrange(4), round(strength[away] * rng.random() * 2))
                    gid += 1
                    games.append(bt.G(gid, when, 135, season, home, away, hg, ag, min(hg, 1), min(ag, 1), None, None))
                when += timedelta(days=15)
    return games


def target_week(games: list[bt.G]) -> list[bt.G]:
    start = dr.week_start(MONDAY)
    return [g for g in games if start <= g.date < start + timedelta(days=7)]


def run(games: list[bt.G], targets: list[bt.G]) -> list[dict]:
    return dr.replay_studies(dr.Vault(games), [dr.fixture_of(g) for g in targets], {}, log=lambda _: None)


def test_a_fixture_carries_no_result():
    assert not {"hg", "ag", "hh", "ha"} & set(dr.Fixture.__dataclass_fields__)


def test_the_vault_never_hands_over_a_game_from_that_moment_on():
    games = league()
    past = dr.Vault(games).before(MONDAY, 135)
    assert past and all(g.date < MONDAY for g in past)
    assert len(past) == sum(g.date < MONDAY for g in games)


def test_changing_every_result_from_that_week_on_changes_nothing():
    games = league()
    targets = target_week(games)
    assert targets
    start = dr.week_start(MONDAY)
    rng = random.Random(1)
    rewritten = [replace(g, hg=rng.randrange(6), ag=rng.randrange(6), hh=0, ha=0) if g.date >= start else g for g in games]
    before = run(games, targets)
    assert before  # la prova ha senso solo se ci sono studi da confrontare
    assert dr.seal(before) == dr.seal(run(rewritten, targets))


def test_changing_a_past_result_does_change_the_study():
    """Controllo della prova: se anche il passato non contasse, quella sopra non dimostrerebbe niente."""
    games = league()
    targets = target_week(games)
    start = dr.week_start(MONDAY)
    last = [g.id for g in games if g.date < start][-30:]
    rewritten = [replace(g, hg=g.hg + 4, ag=0, hh=g.hh, ha=0) if g.id in last else g for g in games]
    assert dr.seal(run(games, targets)) != dr.seal(run(rewritten, targets))


def study(sid: int, when: datetime, *picks: dict) -> dict:
    return {"id": sid, "when": when.isoformat(), "league": 135, "season": 2024, "lam": 1.5, "mu": 1.0, "picks": list(picks)}


def pick(market: str, selection: str, p: float, level: str = "equilibrato", price: float | None = None) -> dict:
    return {"market": market, "selection": selection, "level": level, "p_model": p, "p_archie": p, "evidence": [6, 10, 6, 10],
            "prices": {"sisal": price} if price else {}, "traits": [], "caution": [], "p_book": None, "from_market": True}  # fmt: skip


SATURDAY = datetime(2025, 3, 8, 20, tzinfo=UTC)
GAME = bt.G(1, SATURDAY, 135, 2024, 1, 2, 2, 1, 1, 0, None, None)


def test_a_board_is_published_without_outcomes_then_opened_with_them():
    slips = dr.replay_board([study(1, SATURDAY, pick("OU2.5", "over", 0.62, price=1.7))], {}, date(2025, 3, 8), date(2025, 3, 8))
    giorno = next(s for s in slips if s["kind"] == "giorno")
    assert giorno["legs"][0]["status"] == "open"
    assert giorno["legs"][0]["real_price"] is True
    settled = dr.open_seal(slips, dr.seal(slips), [GAME])
    assert next(s for s in settled if s["kind"] == "giorno")["status"] == "won"  # 2-1: Over 2.5


def test_a_game_already_started_at_ten_is_not_on_the_board():
    morning = datetime(2025, 3, 8, 8, tzinfo=UTC)  # le 9 in Italia: prima della pubblicazione delle 10
    assert dr.replay_board([study(1, morning, pick("OU2.5", "over", 0.62))], {}, date(2025, 3, 8), date(2025, 3, 8)) == []


def test_a_broken_seal_is_refused():
    slips = dr.replay_board([study(1, SATURDAY, pick("OU2.5", "over", 0.62))], {}, date(2025, 3, 8), date(2025, 3, 8))
    fingerprint = dr.seal(slips)
    slips[0]["legs"][0]["selection"] = "under"
    with pytest.raises(ValueError):
        dr.open_seal(slips, fingerprint, [GAME])


def test_leg_lines_count_hits_expected_and_real_price_return():
    slips = [{"kind": "giorno", "legs": [
        {"market": "OU2.5", "status": "won", "p": 0.6, "price": 1.8, "real_price": True},
        {"market": "OU2.5", "status": "lost", "p": 0.6, "price": 1.8, "real_price": True},
        {"market": "OU2.5", "status": "won", "p": 0.6, "price": 1.67, "real_price": False},
    ]}]  # fmt: skip
    line = dr.leg_lines(slips, lambda _, leg: leg["market"])[0]
    assert (line.n, line.won, line.real_n) == (3, 2, 2)
    assert line.expected == pytest.approx(1.8)
    assert line.real_roi == pytest.approx((0.8 - 1.0) / 2)  # la quota stimata non entra nel rendimento


def test_priced_roi_removes_the_margin_only_where_the_price_is_estimated():
    won = {"kind": "giorno", "status": "won", "legs": [
        {"status": "won", "price": 2.0, "real_price": True},
        {"status": "won", "price": 2.0, "real_price": False},
    ]}  # fmt: skip
    assert dr.priced_roi(won, margin=0.1) == pytest.approx(2.0 * 1.8 - 1)
    assert KINDS["giorno"].level == "equilibrato"
