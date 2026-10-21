"""Regolamento personale (D114)."""

from decimal import Decimal
from types import SimpleNamespace as NS

from app.betting.rules import DraftSelection, Rule, describe, suggest, violations


def match(code="ITA-A", home=1, away=2):
    return NS(competition=NS(code=code, name="Serie A"), home_team_id=home, away_team_id=away, home_team=NS(name="Napoli"), away_team=NS(name="Roma"))


def test_violations():
    sels = [DraftSelection(match(), "OU2.5", "over", 1.9), DraftSelection(match("ITA-C-A", 3, 4), "1X2", "1", 2.5),
            DraftSelection(match(home=7), "GG", "yes", 1.8), DraftSelection(match(), "1X2", "2", 3.1)]  # fmt: skip
    rules = [Rule("max_legs", "3"), Rule("max_total_odds", "20"), Rule("max_stake", "10"), Rule("avoid_market", "OU2.5"),
             Rule("avoid_competition", "ITA-C-A"), Rule("avoid_team", "7"), Rule("no_low_price", "")]  # fmt: skip
    out = violations(rules, Decimal("15"), sels, lambda s: -0.06 if s.market == "GG" else 0.01, {7: "Bari"})
    assert len(out) == 7
    assert out[0] == "Al massimo 3 partite per schedina: questa ne ha 4."
    assert "26.51" in out[1]  # 1,9 × 2,5 × 1,8 × 3,1 = 26,505 (virgola mobile: 26,50500…01)
    assert out[5].startswith("Niente partite di Bari")
    assert "-6.0%" in out[6]
    assert violations(rules[:1], Decimal("5"), sels[:2], lambda s: None) == []
    assert describe(Rule("avoid_market", "DC")) == "Evita il mercato doppia chance"


def bet(status, legs, clv, market="1X2", code="ITA-B", stake="10", payout="0"):
    sels = [NS(market=market, clv=Decimal(str(clv)), match=NS(competition=NS(code=code))) for _ in range(legs)]
    return NS(status=status, selections=sels, stake=Decimal(stake), payout=Decimal(payout))


def test_suggestions_need_enough_data():
    few = [bet("lost", 1, -0.05) for _ in range(5)]
    assert suggest(few) == []
    many = [bet("lost", 1, -0.05, market="GG") for _ in range(12)] + [bet("won", 1, 0.03, market="1X2", code="ITA-A", payout="20") for _ in range(12)]
    kinds = {(r.kind, r.value) for r in suggest(many)}
    assert ("avoid_market", "GG") in kinds and ("avoid_competition", "ITA-B") in kinds
    assert ("avoid_market", "1X2") not in kinds and ("no_low_price", "") not in kinds  # in media CLV -1%: sopra la soglia
    long = [bet("lost", 4, 0.01) for _ in range(8)]
    assert ("max_legs", "3") in {(r.kind, r.value) for r in suggest(long)}


def test_rules_api(logged_client, db):
    from datetime import UTC, datetime, timedelta

    from app.models import Competition, Match, Team

    comp = Competition(code="ITA-A", name="Serie A", country="Italia", tier=1)
    a, b = Team(name="Napoli", country="Italia"), Team(name="Roma", country="Italia")
    db.add_all([comp, a, b])
    db.flush()
    m = Match(competition_id=comp.id, season="2026/27", kickoff_at=datetime.now(UTC) + timedelta(days=2), kickoff_has_time=True, home_team_id=a.id, away_team_id=b.id)
    db.add(m)
    db.commit()
    assert logged_client.post("/api/rules", json={"kind": "max_legs", "value": "zero"}).status_code == 422
    rule = logged_client.post("/api/rules", json={"kind": "avoid_team", "value": str(a.id)}).json()
    assert rule["text"] == "Niente partite di Napoli"
    draft = {"stake": "10", "selections": [{"match_id": m.id, "market": "1X2", "pick": "1", "odds": 2.0}]}
    assert logged_client.post("/api/rules/check", json=draft).json()["warnings"] == ["Niente partite di Napoli: c'è Napoli-Roma."]
    assert logged_client.patch(f"/api/rules/{rule['id']}", json={"active": False}).status_code == 200
    assert logged_client.post("/api/rules/check", json=draft).json()["warnings"] == []
    body = logged_client.get("/api/rules").json()
    assert body["rules"][0]["active"] is False and body["suggestions"] == [] and body["style"] is None
    assert logged_client.delete(f"/api/rules/{rule['id']}").status_code == 204
    assert logged_client.post("/api/rules/style").status_code == 422  # nessuna giocata
