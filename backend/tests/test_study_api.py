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


def test_match_study_gives_the_best_picks_per_level_with_reasons(logged_client, seeded, db):  # noqa: F811
    mid = match_id(db, "Milan", "Inter")
    cauto = pick("1T_OU0.5", "over", 0.8) | {"level": "cauto", "reasons": ["Il modello dei gol dà l'80%."]}
    db.add(MatchStudy(match_id=mid, computed_at=datetime.now(UTC), data={"picks": [pick("1X2", "2", 0.6), pick("GG", "yes", 0.66), cauto]}))
    db.commit()
    body = logged_client.get(f"/api/study/match/{mid}").json()
    assert [leg["market"] for leg in body["equilibrato"]] == ["GG", "1X2"]  # il più solido per primo
    assert body["cauto"][0]["reasons"] == ["Il modello dei gol dà l'80%."] and body["rischioso"] == []


def test_target_odds_adds_legs_until_reached(logged_client, seeded, db):  # noqa: F811
    now = datetime.now(UTC)
    db.add(MatchStudy(match_id=match_id(db, "Milan", "Inter"), computed_at=now, data={"picks": [pick("GG", "yes", 0.6) | {"prices": {"sisal": 1.8}}]}))
    db.add(MatchStudy(match_id=match_id(db, "Palermo", "Bari"), computed_at=now, data={"picks": [pick("OU2.5", "under", 0.58)]}))
    db.commit()
    body = logged_client.get("/api/study/multiple?horizon=week&target=1.5").json()
    assert len(body["legs"]) == 1 and body["total_odds"] == 1.8 and body["target_reached"]
    body = logged_client.get("/api/study/multiple?horizon=week&target=50").json()
    assert len(body["legs"]) == 2 and not body["target_reached"]  # solo due partite: a 50 non ci arriva
    assert body["total_odds"] == round(1.8 / 0.58, 2)  # dove manca la quota vale quella giusta dello studio


def test_chosen_days_and_several_competitions(logged_client, seeded, db):  # noqa: F811
    from app.api.picks import ROME
    from app.models import Match

    now = datetime.now(UTC)
    milan, palermo = match_id(db, "Milan", "Inter"), match_id(db, "Palermo", "Bari")
    db.add(MatchStudy(match_id=milan, computed_at=now, data={"picks": [pick("GG", "yes", 0.6)]}))
    db.add(MatchStudy(match_id=palermo, computed_at=now, data={"picks": [pick("OU2.5", "under", 0.62)]}))
    db.commit()
    day = db.get(Match, milan).kickoff_at.replace(tzinfo=UTC).astimezone(ROME).date().isoformat()
    body = logged_client.get(f"/api/study/multiple?days={day}&legs=5").json()
    assert milan in [leg["match"]["id"] for leg in body["legs"]]
    codes = ",".join(c["code"] for c in logged_client.get("/api/competitions").json())
    body = logged_client.get(f"/api/study/multiple?horizon=week&legs=5&competitions={codes}").json()
    assert len(body["legs"]) == 2
    assert logged_client.get("/api/study/multiple?days=ieri").status_code == 422
