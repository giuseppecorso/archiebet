"""Pronostici: fonte migliore per mercato (mercato prima, modello dove manca) ed etichette delle quote."""

from datetime import UTC, datetime

import pytest

from app.api.picks import horizon_end
from app.forecast.demargin import shin
from app.forecast.picks import best_probabilities, favorite, match_picks, off_line, price_verdict
from app.forecast.service import refresh_predictions
from app.models import Match
from tests.test_football_api import match_id, seeded  # noqa: F401 (fixture condivisa)
from tests.test_radar_service import set_odds

PIN = {"1X2": {"1": 2.0, "X": 3.6, "2": 4.0}}  # giuste con Shin ≈ 0,4897 / 0,2690 / 0,2414
MODEL = {"1X2": {"1": 0.5, "X": 0.3, "2": 0.2}, "OU2.5": {"over": 0.55, "under": 0.45}, "GG": {"yes": 0.6, "no": 0.4}}


def test_price_verdict_thresholds():
    assert price_verdict(0.02, 2.0) == "valore"  # a quota 2 basta il 2%
    assert price_verdict(0.019, 2.0) == "nella norma"
    assert price_verdict(0.03, 3.8) == "nella norma"  # a quota 3,8 serve il 3,35% (D72)
    assert price_verdict(0.30, 4.5) == "nella norma"  # oltre quota 4 mai "valore"
    assert price_verdict(-0.05, 2.0) == "nella norma"
    assert price_verdict(-0.051, 2.0) == "paga poco"


def test_market_first_then_model():
    book = {"pinnacle": PIN, "market_avg": {"OU2.5": {"over": 1.8, "under": 2.0}}}
    probs = best_probabilities(book, MODEL)
    assert probs["1X2"][0] == "pinnacle"
    assert probs["1X2"][1]["1"] == pytest.approx(shin([2.0, 3.6, 4.0])[0])  # margine tolto con Shin (D72)
    # Under/Over: niente Pinnacle né Betfair → media di mercato senza margine, non il modello
    assert probs["OU2.5"][0] == "market_avg"
    assert probs["OU2.5"][1]["over"] == pytest.approx(shin([1.8, 2.0])[0])
    # Doppia chance dalla stessa fonte dell'1X2
    assert probs["DC"][0] == "pinnacle"
    assert probs["DC"][1]["1X"] == pytest.approx(probs["1X2"][1]["1"] + probs["1X2"][1]["X"])


def test_model_only_where_market_is_missing():
    probs = best_probabilities({}, MODEL)  # es. Serie C senza quote
    assert probs["1X2"] == ("archie", MODEL["1X2"])
    assert probs["OU2.5"][0] == "archie"
    assert best_probabilities({}, None) == {}


def test_match_picks_with_both_bookmakers_and_favorite():
    book = {"pinnacle": PIN, "sisal": {"1X2": {"1": 2.1, "X": 3.3, "2": 3.6}}, "eurobet": {"1X2": {"1": 2.0}}}
    picks = match_picks(book, None, ("sisal", "eurobet"))
    assert [p.market for p in picks] == ["1X2", "DC"]
    one = picks[0]
    p1 = shin([2.0, 3.6, 4.0])[0]
    sisal, eurobet = one.offers["1"]
    assert (sisal.bookmaker, sisal.price, sisal.verdict) == ("sisal", 2.1, "valore")  # 0,4897 × 2,1 − 1 = +2,8% (soglia 2,1%)
    assert sisal.value == pytest.approx(p1 * 2.1 - 1)
    assert (eurobet.bookmaker, eurobet.verdict) == ("eurobet", "nella norma")  # 0,4897 × 2,0 − 1 = −2,1%
    assert one.offers["2"][0].verdict == "paga poco"  # 0,2414 × 3,6 − 1 = −13,1%
    assert "X" in one.offers and "1X" not in picks[1].offers  # niente quote di doppia chance: nessuna offerta
    assert favorite(picks) == ("1", pytest.approx(p1))
    assert favorite([]) is None


def test_picks_api(logged_client, seeded, db):  # noqa: F811
    milan_inter, palermo_bari = match_id(db, "Milan", "Inter"), match_id(db, "Palermo", "Bari")
    set_odds(db, milan_inter, "pinnacle", {"1": 3.0, "X": 3.5, "2": 2.4})
    set_odds(db, milan_inter, "sisal", {"1": 3.1, "X": 3.3, "2": 2.2})
    refresh_predictions(db, datetime.now(UTC))
    body = logged_client.get("/api/picks").json()
    assert body["bookmakers"] == ["Sisal", "Eurobet"]
    by_match = {p["match"]["id"]: p for p in body["picks"]}
    mi = by_match[milan_inter]
    one = next(m for m in mi["markets"] if m["market"] == "1X2")
    assert (one["source"], one["from_model"], mi["favorite"]) == ("Pinnacle", False, "2")
    assert one["offers"]["1"][0]["bookmaker"] == "Sisal"
    # Under/Over: nessuna quota di mercato → modello di Archie
    ou = next(m for m in mi["markets"] if m["market"] == "OU2.5")
    assert ou["from_model"] is True and ou["source"] == "Modello di Archie"
    # Palermo-Bari: solo la media di mercato di football-data (2,1 / 3,1 / 3,7), senza quote di Sisal
    pb = by_match[palermo_bari]
    assert next(m for m in pb["markets"] if m["market"] == "1X2")["source"] == "Media mercato"
    assert pb["favorite"] == "1" and pb["signals"] == 0


def test_double_chance_and_goal_offers():
    book = {
        "pinnacle": PIN | {"GG": {"yes": 1.8, "no": 2.0}},
        "sisal": {"DC": {"1X": 1.35, "X2": 2.0}, "GG": {"yes": 1.95, "no": 1.8}},
    }
    picks = {p.market: p for p in match_picks(book, None, ("sisal",))}
    p1x = sum(shin([2.0, 3.6, 4.0])[:2])  # 1X dall'1X2 di Pinnacle: 0,7586
    [dc] = picks["DC"].offers["1X"]
    assert picks["DC"].probabilities["1X"] == pytest.approx(p1x)
    assert dc.value == pytest.approx(p1x * 1.35 - 1)  # +2,4%: sopra l'1,5% richiesto a quota 1,35
    assert dc.verdict == "valore"
    gg = picks["GG"]
    assert gg.source == "pinnacle" and gg.probabilities["yes"] == pytest.approx(shin([1.8, 2.0])[0])
    assert gg.offers["yes"][0].value == pytest.approx(gg.probabilities["yes"] * 1.95 - 1)


def test_off_line_prices():
    book = {"pinnacle": PIN, "sisal": {"1X2": {"1": 2.1, "X": 4.0, "2": 5.0}}, "eurobet": {"1X2": {"2": 4.5}}}
    lines = off_line(match_picks(book, None, ("sisal", "eurobet")))
    # 2: 0,2414 × 5,0 − 1 = +20,7% (Sisal) e × 4,5 = +8,6% (Eurobet); X: 0,2690 × 4,0 − 1 = +7,6% non basta
    assert [(l.selection, l.offer.bookmaker) for l in lines] == [("2", "sisal"), ("2", "eurobet")]
    assert lines[0].offer.value == pytest.approx(shin([2.0, 3.6, 4.0])[2] * 5.0 - 1)


def test_off_line_api_only_today(logged_client, seeded, db):  # noqa: F811
    milan_inter = match_id(db, "Milan", "Inter")  # tra 3 giorni: non è "oggi"
    set_odds(db, milan_inter, "pinnacle", {"1": 3.0, "X": 3.5, "2": 2.4})
    set_odds(db, milan_inter, "sisal", {"1": 4.0, "X": 3.3, "2": 2.2})  # 1: +28%
    assert logged_client.get("/api/picks/off-line").json() == []
    match = db.get(Match, milan_inter)
    now = datetime.now(UTC)
    match.kickoff_at = now + (horizon_end(now, "today") - now) / 2  # sempre prima della mezzanotte italiana
    db.commit()
    [row] = logged_client.get("/api/picks/off-line").json()
    assert (row["selection"], row["bookmaker"], row["suspicious"]) == ("1", "Sisal", True)


def test_model_only_estimates_never_say_value():
    from app.forecast.picks import MODEL_SOURCE, price_verdict

    assert price_verdict(0.10, 2.0) == "valore"
    assert price_verdict(0.10, 2.0, MODEL_SOURCE) == "nella norma"  # batte solo il modello: niente segnale (D99)
    assert price_verdict(-0.10, 2.0, MODEL_SOURCE) == "paga poco"


def test_multiple_skips_model_only_legs():
    from datetime import UTC, datetime

    from app.forecast.picks import MODEL_SOURCE, MarketPick, Offer
    from app.forecast.picks_service import legs_for

    class M:
        id, kickoff_at = 1, datetime(2026, 10, 24, tzinfo=UTC)

    model = MarketPick("1X2", MODEL_SOURCE, {"1": 0.5}, {"1": [Offer("sisal", 2.2, 0.1, "nella norma")]})
    market = MarketPick("OU2.5", "pinnacle", {"over": 0.5}, {"over": [Offer("sisal", 2.0, 0.0, "nella norma")]})
    assert [(leg.market, leg.selection) for leg in legs_for([(M, [model, market])], "sisal")] == [("OU2.5", "over")]


def test_without_sharp_odds_the_italian_consensus_beats_the_model():
    from app.forecast.picks import CONSENSUS_SOURCE, CONSENSUS_VALUE, best_probabilities, italian_consensus, price_verdict

    book = {"sisal": {"1X2": {"1": 2.0, "X": 3.2, "2": 3.8}}, "eurobet": {"1X2": {"1": 2.1, "X": 3.1, "2": 3.6}}}
    model = {"1X2": {"1": 0.6, "X": 0.2, "2": 0.2}}
    source, probs = best_probabilities(book, model)["1X2"]
    assert source == CONSENSUS_SOURCE  # Serie C: la media dei bookmaker italiani prima del modello (D95-D96)
    assert sum(probs.values()) == pytest.approx(1.0)
    assert italian_consensus({"sisal": book["sisal"]}, "1X2") is None  # con un solo bookmaker non si fa la media
    assert best_probabilities({"sisal": book["sisal"]}, model)["1X2"][0] == "archie"
    assert price_verdict(0.10, 2.0, CONSENSUS_SOURCE) == CONSENSUS_VALUE
