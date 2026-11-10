import json

from app.api.strategies import RESULTS, load_results
from app.forecast import market_strategies as ms


def test_missing_file_gives_an_empty_list(tmp_path):
    assert load_results(tmp_path / "nothing.json") == {"generated_at": None, "strategies": []}


def test_saved_results_cover_every_strategy():
    data = load_results(RESULTS)
    assert {s["key"] for s in data["strategies"]} == {s.key for s in ms.STRATEGIES}
    for s in data["strategies"]:
        assert set(s) >= {"name", "how", "price", "passed", "beats_close", "tuning", "confirm"}


def test_reads_a_saved_file(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"generated_at": "x", "strategies": [{"key": "home"}]}), encoding="utf-8")
    assert load_results(path)["strategies"] == [{"key": "home"}]
