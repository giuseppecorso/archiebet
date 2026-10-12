"""Dove vinci e dove perdi: schedine costruite a mano (senza database), valori calcolati a mano."""

from decimal import Decimal as D

from app.betting.analysis import breakdown, size_label
from app.models import Bet, BetSelection, Competition, Match, Team

SERIE_A = Competition(name="Serie A")
SERIE_C = Competition(name="Serie C · Girone C")


def match(home: str, away: str, competition: Competition) -> Match:
    return Match(home_team=Team(name=home), away_team=Team(name=away), competition=competition)


def sel(m: Match, market: str, odds: str, status: str, clv: str | None = None) -> BetSelection:
    return BetSelection(match=m, market=market, pick="1", odds=D(odds), status=status, clv=D(clv) if clv else None)


INTER_ROMA = match("Inter", "Roma", SERIE_A)
MILAN_LAZIO = match("Milan", "Lazio", SERIE_A)
CATANIA_BARI = match("Catania", "Bari", SERIE_C)

BETS = [
    # Singola vinta: 10 € a 2,00 → torna 20 (+10)
    Bet(stake=D("10"), total_odds=D("2.00"), bookmaker="Snai", status="won", payout=D("20.00"),
        selections=[sel(INTER_ROMA, "1X2", "2.00", "won", "0.05")]),
    # Singola persa: 10 € → 0 (-10)
    Bet(stake=D("10"), total_odds=D("1.80"), bookmaker="Snai", status="lost", payout=D("0"),
        selections=[sel(MILAN_LAZIO, "OU2.5", "1.80", "lost", "-0.02")]),
    # Doppia persa per una sola selezione: 5 € → 0 (-5); la selezione di Serie C era vinta
    Bet(stake=D("5"), total_odds=D("3.30"), bookmaker="Sisal", status="lost", payout=D("0"),
        selections=[sel(INTER_ROMA, "1X2", "1.50", "lost"), sel(CATANIA_BARI, "GG", "2.20", "won")]),
    # Singola aperta: non entra nei rendimenti, sì nelle abitudini
    Bet(stake=D("4"), total_odds=D("1.90"), bookmaker=None, status="open", payout=None,
        selections=[sel(CATANIA_BARI, "1X2", "1.90", "open")]),
]  # fmt: skip


def by_label(groups):
    return {g.label: g for g in groups}


def test_size_labels():
    assert [size_label(n) for n in (1, 2, 3, 4, 7)] == ["Singole", "Doppie", "Triple", "4 o più partite", "4 o più partite"]


def test_by_size_uses_whole_bets():
    groups = by_label(breakdown(BETS).by_size)
    singles = groups["Singole"]
    assert (singles.bets, singles.won, singles.staked, singles.profit, singles.roi) == (2, 1, D("20"), D("0.00"), 0.0)
    doubles = groups["Doppie"]
    assert (doubles.bets, doubles.profit, doubles.roi) == (1, D("-5"), -1.0)


def test_by_bookmaker():
    groups = by_label(breakdown(BETS).by_bookmaker)
    assert groups["Snai"].profit == D("0.00") and groups["Sisal"].roi == -1.0
    assert "Non indicato" not in groups  # l'unica senza bookmaker è ancora aperta


def test_by_competition_counts_each_selection():
    groups = by_label(breakdown(BETS).by_competition)
    a = groups["Serie A"]  # Inter-Roma 2,00 vinta, Milan-Lazio 1,80 persa, Inter-Roma 1,50 persa
    assert (a.selections, a.won, a.hit_rate) == (3, 1, 0.3333)
    assert a.avg_odds == 1.77  # (2,00 + 1,80 + 1,50) / 3
    assert a.flat_roi == -0.3333  # come singole a 1 €: torna 2,00 su 3 giocati → -1/3
    assert a.avg_clv == 0.015 and a.clv_count == 2  # (+5% - 2%) / 2
    c = groups["Serie C · Girone C"]  # la selezione vinta nella doppia persa conta come vinta
    assert (c.selections, c.won, c.flat_roi, c.avg_clv) == (1, 1, 1.2, None)


def test_by_market():
    groups = by_label(breakdown(BETS).by_market)
    assert set(groups) == {"Esito finale", "Under / Over 2.5", "Goal / NoGoal"}
    assert groups["Esito finale"].selections == 2  # la selezione aperta non conta


def test_habits():
    h = breakdown(BETS).habits
    assert h.bets == 4
    assert h.avg_stake == D("7.25")  # (10+10+5+4)/4
    assert h.avg_odds == 2.25  # (2,00+1,80+3,30+1,90)/4
    assert h.multiple_share == 0.25
    assert h.avg_selections == 1.25
    assert h.top_market == "Esito finale"  # 3 selezioni su 5
    assert h.top_bookmaker == "Snai"
    assert h.top_teams[0] in (("Inter", 2), ("Roma", 2), ("Catania", 2), ("Bari", 2))


def test_empty():
    b = breakdown([])
    assert b.by_size == [] and b.habits.avg_stake is None and b.habits.top_teams == []
