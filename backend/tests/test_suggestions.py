"""I due pronostici della pagina partita (D107)."""

from app.forecast.picks import MarketPick, Offer
from app.forecast.suggestions import suggestions


def pick(market, probs, prices, verdicts=None):
    verdicts = verdicts or {}
    offers = {s: [Offer("sisal", prices[s], probs[s] * prices[s] - 1, verdicts.get(s, "nella norma"))] for s in prices}
    return MarketPick(market, "pinnacle", probs, offers)


def test_safe_is_the_most_likely_with_a_playable_price_and_bold_prefers_value():
    picks = [
        pick("1X2", {"1": 0.55, "X": 0.25, "2": 0.20}, {"1": 1.75, "X": 3.6, "2": 4.8}),
        pick("DC", {"1X": 0.80, "X2": 0.45, "12": 0.75}, {"1X": 1.22, "X2": 2.1, "12": 1.30}),  # 1X a 1,22: troppo bassa
        pick("OU2.5", {"over": 0.48, "under": 0.52}, {"over": 2.05, "under": 1.80}),
        pick("GG", {"yes": 0.40, "no": 0.60}, {"yes": 2.70, "no": 1.45}, {"yes": "valore"}),
    ]
    safe, bold = suggestions(picks)
    assert (safe.kind, safe.market, safe.selection) == ("sicuro", "DC", "12")  # 75% a 1,30
    assert (bold.kind, bold.market, bold.selection, bold.has_value) == ("spinto", "GG", "yes", True)


def test_bold_without_value_is_the_most_likely_between_2_and_4():
    picks = [pick("1X2", {"1": 0.45, "X": 0.28, "2": 0.27}, {"1": 2.10, "X": 3.40, "2": 3.50}),
             pick("OU2.5", {"over": 0.52, "under": 0.48}, {"over": 1.85, "under": 1.95})]  # fmt: skip
    safe, bold = suggestions(picks)
    assert (safe.market, safe.selection) == ("OU2.5", "over")
    assert (bold.market, bold.selection, bold.has_value) == ("1X2", "1", False)


def test_no_prices_no_suggestions_and_no_duplicate():
    assert suggestions([MarketPick("1X2", "pinnacle", {"1": 0.5, "X": 0.3, "2": 0.2}, {})]) == []
    only = suggestions([pick("1X2", {"1": 0.40, "X": 0.30, "2": 0.30}, {"1": 2.4})])
    assert [s.kind for s in only] == ["sicuro"]  # la stessa scelta non si ripete come "spinta"
