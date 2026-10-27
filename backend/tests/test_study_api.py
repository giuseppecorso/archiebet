"""Fammi una multipla: le multiple a tema (campionati e mercati)."""

from datetime import UTC, datetime

from app.models import MatchStudy
from tests.test_football_api import match_id, seeded  # noqa: F401 (fixture condivisa)


def pick(market, selection, p):
    return {"market": market, "selection": selection, "level": "equilibrato", "event": f"{market} {selection}", "p_model": p, "p_archie": p,
            "evidence": [5, 10, 5, 10], "reasons": [], "prices": {}, "traits": [], "caution": []}  # fmt: skip


def legs(client, theme):
    body = client.get(f"/api/study/multiple?horizon=week&legs=5&theme={theme}").json()
    return [(leg["match"]["home"]["name"], leg["market"]) for leg in body["legs"]]


def test_themes_filter_leagues_and_markets(logged_client, seeded, db):  # noqa: F811
    now = datetime.now(UTC)
    db.add(MatchStudy(match_id=match_id(db, "Milan", "Inter"), computed_at=now, data={"picks": [pick("1X2", "2", 0.6), pick("1T_OU0.5", "over", 0.7)]}))
    db.add(MatchStudy(match_id=match_id(db, "Palermo", "Bari"), computed_at=now, data={"picks": [pick("OU2.5", "under", 0.62)]}))
    db.commit()
    assert legs(logged_client, "tutte") == [("Milan", "1T_OU0.5"), ("Palermo", "OU2.5")]
    assert legs(logged_client, "maggiori") == [("Milan", "1T_OU0.5")]  # Serie A
    assert legs(logged_client, "minori") == [("Palermo", "OU2.5")]  # Serie B
    assert legs(logged_client, "primo_tempo") == [("Milan", "1T_OU0.5")]
    assert legs(logged_client, "coppe") == []
    assert legs(logged_client, "notizie") == []  # nessuna notizia raccolta
    assert "coppe" in logged_client.get("/api/study/themes").json()
