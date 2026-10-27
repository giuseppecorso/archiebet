"""Lo studio di Archie (D137): modello dei gol, primo tempo, fatti del campo, livelli e multipla."""

import math

import pytest

from app.betting.calc import LOST, WON, market_name, selection_outcome
from app.forecast import study as st


def test_model_probabilities_are_coherent():
    probs = st.model_probabilities(1.5, 1.0, -0.05, 0.45, 0.42)
    assert sum(probs["1X2"].values()) == pytest.approx(1)
    assert probs["OU2.5"]["over"] + probs["OU2.5"]["under"] == pytest.approx(1)
    assert probs["1T_TGH0.5"]["over"] == pytest.approx(1 - math.exp(-1.5 * 0.45))  # gol di casa nel primo tempo
    assert probs["1T_OU0.5"]["under"] == pytest.approx(math.exp(-(1.5 * 0.45 + 1.0 * 0.42)))
    assert probs["MG2-5"]["yes"] > probs["MG2-4"]["yes"]
    assert probs["CB_1X_O1.5"]["yes"] < probs["DC"]["1X"]


def test_first_half_share_shrinks_to_league():
    assert st.first_half_share(0, 0, 0.44) == pytest.approx(0.44)  # nessun gol: la media del campionato
    assert 0.44 < st.first_half_share(15, 20, 0.44) < 0.75  # 15 gol su 20 nel primo tempo: sale, ma con prudenza


def test_hits_from_each_side():
    home = [st.Played(2, 0, 1, 0), st.Played(1, 1, 0, 1), st.Played(0, 2, 0, 1)]  # partite in casa della squadra di casa
    away = [st.Played(0, 3, 0, 2), st.Played(1, 1, 1, 0)]  # partite in trasferta dell'ospite (fatti, subiti)
    assert st.hits("1T_TGH0.5", "over", home, True) == 1  # la squadra di casa ha segnato nel primo tempo una volta
    assert st.hits("1T_TGH0.5", "over", away, False) == 1  # l'ospite ha subito nel primo tempo una volta
    assert st.hits("GG", "yes", away, False) == 1


def test_archie_probability_is_a_bayesian_mix():
    ev = st.Evidence(8, 10, 7, 10)  # 15 volte su 20
    p = st.archie_probability(0.60, ev)
    assert p == pytest.approx((0.60 * st.PRIOR_GAMES + 15) / (st.PRIOR_GAMES + 20))
    assert 0.60 < p < 0.75  # i fatti spostano il modello, non lo ribaltano


def _games(scored, conceded, n=10, s1=None, c1=None):
    return [st.Played(scored, conceded, scored if s1 is None else s1, conceded if c1 is None else c1) for _ in range(n)]


def test_picks_need_model_and_field_agreeing():
    probs = st.model_probabilities(2.4, 0.9, -0.05, 0.45, 0.45)  # anche il modello crede al gol di casa nel primo tempo (66%)
    # La casa segna sempre nel primo tempo in casa, l'ospite subisce sempre nel primo tempo in trasferta
    picks = st.study_picks(probs, _games(2, 1, s1=1, c1=0), _games(1, 2, s1=0, c1=1), "Brescia", "Cittadella")
    by = {(p.market, p.selection): p for p in picks}
    first = by[("1T_TGH0.5", "over")]
    assert first.event == "Brescia segna nel primo tempo"
    assert first.evidence == st.Evidence(10, 10, 10, 10)
    assert "10 su 10 partite in casa del Brescia" in first.reasons[0]
    # Vittoria dell'ospite: il modello non ci crede e il campo nemmeno → mai proposta
    assert ("1X2", "2") not in by
    # Troppe poche partite: nessun pronostico
    assert st.study_picks(probs, _games(2, 1, n=3), _games(1, 2), "A", "B") == []


def test_field_contradiction_excludes_pick():
    probs = st.model_probabilities(1.7, 1.0, -0.05, 0.45, 0.45)
    # Il modello darebbe "casa segna" alto, ma la casa in casa non segna mai
    picks = st.study_picks(probs, _games(0, 1), _games(1, 1), "A", "B")
    assert not any(p.market == "TGH0.5" and p.selection == "over" for p in picks)


def test_choose_multiple_one_leg_per_match_and_exclusions():
    def pick(level, p, prices=None):
        return {"level": level, "p_archie": p, "p_model": p, "evidence": [8, 10, 8, 10], "prices": prices or {}}

    studies = [(1, [pick("cauto", 0.80), pick("cauto", 0.85)]), (2, [pick("cauto", 0.75)]), (3, [pick("rischioso", 0.40)])]
    chosen = st.choose_multiple(studies, "cauto", 5)
    assert [m for m, _ in chosen] == [1, 2] and chosen[0][1]["p_archie"] == 0.85
    assert [m for m, _ in st.choose_multiple(studies, "cauto", 5, {1})] == [2]  # "genera un'altra": partite nuove
    # A parità, prima dove la quota del bookmaker paga più dello studio
    tie = [(1, [pick("cauto", 0.80, {"sisal": 1.20})]), (2, [pick("cauto", 0.80, {"sisal": 1.40})])]
    assert st.choose_multiple(tie, "cauto", 1)[0][0] == 2


def test_study_markets_settle_and_have_names():
    assert selection_outcome("1T_TGH0.5", "over", 1, 2, (1, 0)) == WON
    assert selection_outcome("1T_OU1.5", "under", 3, 1, (1, 1)) == LOST
    assert selection_outcome("MG2-4", "yes", 1, 0) == LOST
    assert selection_outcome("CB_X2_U3.5", "yes", 0, 2) == WON
    with pytest.raises(ValueError):
        selection_outcome("1T_OU0.5", "over", 1, 0)  # serve il primo tempo
    assert market_name("1T_TGA0.5") == "gol ospite Under/Over 0.5 primo tempo"
    assert st.event_text("CB_1X_O1.5", "yes", "Brescia", "Cittadella") == "Brescia non perde e almeno 2 gol"


# --- Correzioni prudenti: notizie, motivazione, meteo (D138) ---


def test_news_adjustment_moves_expected_goals():
    adj = st.news_adjustment("away", "netta", "Il Brescia perde il bomber.", "Brescia", "Cittadella")
    assert (adj.home, adj.away) == pytest.approx((0.94, 1.06))
    assert adj.reasons[0].startswith("Notizie: favoriscono Cittadella (netta)")
    assert st.news_adjustment("none", "", "", "A", "B") == st.Adjustment()


def test_motivation_from_the_table():
    def spot(pos, pts, played=20, top=40, safe=20, teams=20):
        return st.TableSpot(pos, teams, pts, played, top, safe)

    assert st.goal_of(spot(1, 45)) == "vertice"
    assert st.goal_of(spot(18, 19)) == "salvezza"
    assert st.goal_of(spot(10, 28, played=34)) == "nessun obiettivo"  # lontana da tutto con 4 giornate alla fine
    assert st.goal_of(spot(18, 19, played=5)) is None  # a inizio stagione la classifica non dice niente
    adj = st.motivation_adjustment(spot(18, 19, played=34), spot(10, 28, played=34), "Brescia", "Cittadella")
    assert (adj.home, adj.away) == pytest.approx((1.03, 1.0)) and "lotta per la salvezza" in adj.reasons[0]


def test_weather_and_chaining():
    assert st.weather_adjustment(6.0, 10.0).home == pytest.approx(0.96)
    assert st.weather_adjustment(0.0, 40.0).reasons[0].startswith("Meteo previsto: vento forte")
    assert st.weather_adjustment(0.5, 10.0) == st.Adjustment()
    assert st.weather_adjustment(None, None) == st.Adjustment()
    both = st.news_adjustment("home", "lieve", "", "A", "B").then(st.weather_adjustment(6.0, 0.0))
    assert both.home == pytest.approx(1.03 * 0.96) and len(both.reasons) == 2


def test_scorecard_compares_promised_and_won():
    rows = [("2026-10-19", "cauto", 0.80, True), ("2026-10-19", "cauto", 0.80, False), ("2026-10-26", "rischioso", 0.40, True)]
    card = st.scorecard(rows)
    assert card["levels"]["cauto"] == {"picks": 2, "won": 1, "expected": 1.6, "hit_rate": 0.5, "promised": 0.8}
    assert card["levels"]["equilibrato"]["picks"] == 0
    assert [w["week"] for w in card["weeks"]] == ["2026-10-19", "2026-10-26"]
