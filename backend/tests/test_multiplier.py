"""Schedina 6-10 e "Scegli per prezzo" in Fammi una multipla (D177)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.forecast import multiplier as mp
from app.models import MatchOdds, MatchStudy
from tests.test_football_api import match_id, seeded  # noqa: F401 (fixture condivisa)

SHARP = {"1": 2.9, "X": 3.3, "2": 2.4}
OFFERED = {"1": 3.0, "X": 3.2, "2": 2.35}


def odds(db, mid: int) -> None:
    for book, prices in (("pinnacle", SHARP), ("sisal", OFFERED)):
        for selection, price in prices.items():
            db.add(MatchOdds(match_id=mid, source="oddspapi", bookmaker=book, market="1X2", selection=selection, price=price, is_closing=False))


def two_matches(db) -> list[int]:
    ids = [match_id(db, "Milan", "Inter"), match_id(db, "Palermo", "Bari")]
    for mid in ids:
        odds(db, mid)
        db.add(MatchStudy(match_id=mid, computed_at=datetime.now(UTC), data={"picks": []}))
    db.commit()
    return ids


def test_rows_keep_only_markets_with_a_real_price():
    book = {"pinnacle": {"1X2": SHARP, "GG": {"yes": 1.8, "no": 2.0}}, "sisal": {"1X2": OFFERED, "GG": {"yes": 1.9, "no": 1.9}}}
    rows = mp.price_rows(1, "2026-11-10T20:00:00+00:00", book, ("sisal",))
    assert {r["market"] for r in rows} == {"1X2"}
    assert next(r for r in rows if r["selection"] == "1")["price"] == 3.0


def test_rows_need_pinnacle():
    assert mp.price_rows(1, "x", {"betfair_ex": {"1X2": SHARP}, "sisal": {"1X2": OFFERED}}, ("sisal",)) == []


def test_a_custom_range_is_respected():
    rows = [{"match_id": i, "when": "x", "market": "1X2", "selection": "1", "price": 4.0, "sharp": 0.24} for i in range(3)]
    slip = mp.best_slip(rows, 2, "valore", 12.0, 20.0)
    assert slip is not None and 12 <= slip[0]["price"] * slip[1]["price"] <= 20
    assert mp.best_slip(rows, 2, "valore", 6.0, 10.0) is None


@pytest.mark.parametrize(("center", "legs"), [(8, 2), (12, 2), (13, 3), (40, 3), (41, 4)])
def test_archie_keeps_the_legs_few(center, legs):
    assert mp.legs_for(center) == legs


def test_by_price_reaches_the_range_with_real_prices(logged_client, seeded, db):  # noqa: F811
    two_matches(db)
    body = logged_client.get("/api/study/multiple?horizon=week&target=6&target_max=10&by_price=true&auto=true").json()
    assert body["by_price"] is True
    assert len(body["legs"]) == 2
    assert 6 <= body["total_odds"] <= 10 and body["target_reached"]
    assert all(leg["prices"] and leg["reasons"] for leg in body["legs"])


def test_by_price_falls_back_when_no_price_fits(logged_client, seeded, db):  # noqa: F811
    db.add(MatchStudy(match_id=match_id(db, "Milan", "Inter"), computed_at=datetime.now(UTC), data={"picks": []}))
    db.commit()
    body = logged_client.get("/api/study/multiple?horizon=week&target=6&target_max=10&by_price=true&auto=true").json()
    assert body["by_price"] is False


def test_the_board_slip_uses_two_matches_in_the_range(seeded, db):  # noqa: F811
    from app.forecast.daily import KINDS
    from app.forecast.daily_service import multiplier_legs, slip_totals

    two_matches(db)
    now = datetime.now(UTC)
    legs = multiplier_legs(db, KINDS["sei_dieci"], now, now + timedelta(days=30))
    assert len(legs) == 2
    total, probability = slip_totals(KINDS["sei_dieci"], legs)
    assert 6 <= total <= 10 and 0 < probability < 0.2
