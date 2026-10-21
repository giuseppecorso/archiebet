"""Cosa impara Archie (D117-D121)."""

from datetime import UTC, date, datetime

import pytest

from app.forecast import learning_service as ls
from app.forecast import strategy_search as ss
from app.forecast.history_sim import SimMatch


def _sim(mid: int, season: str, p1: float, px: float, hg: int, ag: int, month: int = 10, price1: float = 2.0, league: str = "ITA-A") -> SimMatch:
    fair = {"1X2": {"1": p1, "X": px, "2": 1 - p1 - px}, "OU2.5": {"over": 0.5, "under": 0.5}}
    return SimMatch(mid, season, league, date(2020, month, 1), datetime(2020, month, 1, tzinfo=UTC), hg, ag, fair, fair,
                    {"1X2": {"1": price1, "X": 3.5, "2": 4.0}, "OU2.5": {"over": 1.9, "under": 1.9}})  # fmt: skip


def test_twins_nearest_and_outcomes():
    rows = [["ITA-A", 0.5, 0.3, 0.2, 0.5, 2, 0, "2020-01-01", 1]] * 3 + [["ITA-B", 0.2, 0.3, 0.5, 0.5, 0, 1, "2020-01-02", 2]] * 3
    t = ls.twins({"1": 0.52, "X": 0.28, "2": 0.2}, 0.5, rows=rows, k=3)
    assert t["n"] == 3 and t["observed"] == {"1": 1.0, "X": 0.0, "2": 0.0}
    assert t["expected"]["1"] == pytest.approx(0.5) and t["avg_goals"] == 2
    assert t["over_observed"] == 0.0 and t["top_scores"][0] == ["2-0", 1.0]
    assert t["examples"][0]["match_id"] == 1
    assert ls.twins({"1": 0.5, "X": 0.3, "2": 0.2}, None, rows=[]) is None


def test_value_map_counts_d72_occasions_by_month():
    # bet365 paga 2,0 sull'1 dato al 55% da Pinnacle: valore 10%, sopra la soglia D72
    sims = [_sim(1, "2019/20", 0.55, 0.25, 1, 0, month=9), _sim(2, "2019/20", 0.55, 0.25, 0, 1, month=9), _sim(3, "2019/20", 0.48, 0.27, 1, 1, month=12)]  # nessun esito con valore
    vm = ls.value_map(sims)
    rows = {(r["league"], r["month"]): r for r in vm["rows"]}
    assert rows[("ITA-A", 9)]["count"] == 2 and ("ITA-A", 12) not in rows
    assert vm["plays"] == 2 and vm["seasons"] == 1


def test_calibration_report_flags_bins():
    sims = [_sim(i, "2024/25", 0.6, 0.25, 1 if i % 10 < 6 else 0, 0) for i in range(200)]
    report = ls.calibration_report(sims)
    [row] = [r for r in report["rows"] if r["group"] == "Serie A e B" and r["market"] == "1X2"]
    top = [b for b in row["bins"] if b["low"] == 0.6][0]
    assert top["observed"] == pytest.approx(0.6) and not top["off"]


def test_strategy_roundtrip():
    s = ss.Strategy("ITA-A", "1X2", "2", (4.0, 1000.0), ss.WHOLE, ss.WITH_VALUE)
    assert ls.strategy_from(ls.strategy_dict(s)) == s


def test_learning_api(logged_client, tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "learning_dir", lambda: tmp_path)
    ls.load_learning.cache_clear()
    assert logged_client.get("/api/lab/learning").status_code == 404
    (tmp_path / "learning.json").write_text('{"computed_at": "2026-10-21T12:00:00+00:00", "strategies": {"passed": []}}', encoding="utf-8")
    ls.load_learning.cache_clear()
    assert logged_client.get("/api/lab/learning").json()["computed_at"].startswith("2026-10-21")
    assert ls.passed_strategies() == []
    ls.load_learning.cache_clear()
