"""Io contro Archie: fiuto (vinte − attese), giocate d'accordo / in disaccordo con Archie, lettura della fotografia."""

import math
from datetime import UTC, datetime

import pytest

from app.betting.versus import JudgedPick, archie_probability, versus
from app.forecast.service import refresh_predictions
from app.models import Match
from tests.test_football_api import match_id, seeded  # noqa: F401 (fixture condivisa)


def test_versus_numbers():
    picks = [
        JudgedPick(0.5, 2.2, True),  # valore +10%: Archie d'accordo
        JudgedPick(0.6, 1.8, False),  # +8%: d'accordo
        JudgedPick(0.4, 2.2, True),  # −12%: in disaccordo
        JudgedPick(0.7, 1.3, True),  # −9%: in disaccordo
    ]
    v = versus(picks, without_archie=2)
    assert v.judged == 4 and v.without_archie == 2
    assert v.skill == pytest.approx(3 - (0.5 + 0.6 + 0.4 + 0.7))  # vinte 3, attese 2,2 → +0,8
    assert v.skill_std_error == pytest.approx(math.sqrt(0.25 + 0.24 + 0.24 + 0.21))
    assert (v.agreed.n, v.agreed.won) == (2, 1)
    assert v.agreed.roi == pytest.approx((1.2 - 1) / 2)  # +1,2 e −1 → +0,1 a giocata
    assert v.agreed.avg_value == pytest.approx((0.10 + 0.08) / 2)
    assert v.disagreed.expected_wins == pytest.approx(1.1)
    assert v.disagreed.roi == pytest.approx((1.2 + 0.3) / 2)


def test_versus_empty():
    v = versus([], without_archie=3)
    assert (v.judged, v.without_archie, v.skill, v.agreed) == (0, 3, None, None)


def test_archie_probability_from_snapshot():
    snap = {
        "prediction": {
            "markets": {"1X2": {"1": 0.45, "X": 0.3, "2": 0.25}, "GG": {"yes": 0.55, "no": 0.45}},
            "market": {"1X2": {"source": "Pinnacle · apertura", "probabilities": {"1": 0.5, "X": 0.28, "2": 0.22}}},
        }
    }
    assert archie_probability(snap, "1X2", "1") == 0.5  # il mercato prima del modello
    assert archie_probability(snap, "DC", "1X") == pytest.approx(0.78)  # dall'1X2 di mercato
    assert archie_probability(snap, "GG", "yes") == 0.55  # niente mercato: modello
    assert archie_probability(snap, "OU2.5", "over") is None
    assert archie_probability(None, "1X2", "1") is None  # giocata senza fotografia
    assert archie_probability({"prediction": None}, "1X2", "1") is None


def test_versus_api_uses_the_snapshot(logged_client, seeded, db):  # noqa: F811
    milan_inter = match_id(db, "Milan", "Inter")
    refresh_predictions(db, datetime.now(UTC))  # Archie ha una previsione prima della giocata
    body = {"kind": "real", "stake": "10", "bookmaker": "Sisal",
            "selections": [{"match_id": milan_inter, "market": "1X2", "pick": "2", "odds": "2.50"}]}  # fmt: skip
    assert logged_client.post("/api/bets", json=body).status_code == 201
    snap_p = logged_client.get(f"/api/matches/{milan_inter}").json()["prediction"]["market"]["1X2"]["probabilities"]["2"]

    match = db.get(Match, milan_inter)
    match.status, match.home_goals, match.away_goals = "finished", 0, 2
    db.commit()
    v = logged_client.get("/api/bets/versus").json()
    assert v["judged"] == 1 and v["without_archie"] == 0
    assert v["skill"] == pytest.approx(1 - snap_p)  # vinta, attesa snap_p
    group = v["agreed"] if snap_p * 2.5 >= 1 else v["disagreed"]
    assert (group["n"], group["won"], group["roi"]) == (1, 1, pytest.approx(1.5))
    assert logged_client.get("/api/bets/versus?kind=simulated").json()["judged"] == 0
