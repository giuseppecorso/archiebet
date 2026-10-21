

def test_other_goal_lines():
    import pytest

    from app.forecast.live import outcome_probabilities, selection_probability

    probs = outcome_probabilities(1.4, 1.1)
    assert probs["over1.5"] > probs["over"] > probs["over3.5"] > 0
    # sul 2-1 l'Over 1.5 e 2.5 sono già vinti, l'Over 3.5 manca di un gol
    late = outcome_probabilities(0.3, 0.2, 2, 1)
    assert late["over1.5"] == pytest.approx(1.0) and late["over"] == pytest.approx(1.0) and 0 < late["over3.5"] < 0.5
    assert selection_probability("OU3.5", "under", late) == pytest.approx(1 - late["over3.5"])
