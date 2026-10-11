"""Test del lettore football-data su righe copiate dai file reali."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.adapters.football_data import parse_csv, parse_kickoff, season_code, season_label, season_of

# Formato 2026/27: data a 4 cifre, ora, xG, niente Pinnacle, Betfair Exchange presente
CSV_2026 = (
    "﻿Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HxG,AxG,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,"
    "B365H,B365D,B365A,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,BFEH,BFED,BFEA,B365>2.5,B365<2.5,Avg>2.5,Avg<2.5,"
    "B365CH,B365CD,B365CA,AvgCH,AvgCD,AvgCA\n"
    "I1,22/08/2026,17:30,Inter,Monza,4,1,H,1,1,D,1.05,1.23,13,7,5,3,5,14,3,3,2,2,0,0,"
    "1.2,7,13,1.22,7,15,1.19,6.66,13.73,1.22,7.6,17,1.62,2.3,1.58,2.3,"
    "1.14,8.5,17,1.15,8.1,16\n"
)

# Formato 2012/13: data a 2 cifre, niente ora, Pinnacle con chiusura, BetBrain come max/media
CSV_2012 = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,"
    "B365H,B365D,B365A,PSH,PSD,PSA,BbMxH,BbAvH,BbMxD,BbAvD,BbMxA,BbAvA,BbMx>2.5,BbAv>2.5,BbMx<2.5,BbAv<2.5,PSCH,PSCD,PSCA\n"
    "I1,25/08/12,Fiorentina,Udinese,2,1,H,0,1,A,23,7,8,2,12,14,10,0,2,1,0,0,"
    "2.05,3.2,3.75,2.1,3.32,4.13,2.1,2.05,3.33,3.21,4.15,3.71,2.33,2.2,1.73,1.66,1.97,3.31,4.74\n"
    ",,,,,,,,\n"
)

# Prossime partite: niente risultato
FIXTURES = (
    "﻿Div,Date,Time,HomeTeam,AwayTeam,Referee,B365H,B365D,B365A\n"
    "I1,10/10/2026,19:45,Napoli,Frosinone,,1.44,4.75,7\n"
    "B1,09/10/2026,19:45,Beveren,Lommel SK,,1.75,3.8,3.9\n"
)


def odds_of(match, bookmaker, market, closing=False):
    return {q.selection: q.price for q in match.odds if q.bookmaker == bookmaker and q.market == market and q.is_closing == closing}


def test_seasons():
    assert season_code(2005) == "0506"
    assert season_code(1999) == "9900"
    assert season_label(2025) == "2025/26"
    assert season_label(1999) == "1999/00"
    assert season_of(date(2026, 8, 22)) == 2026
    assert season_of(date(2027, 5, 30)) == 2026


def test_uk_time_becomes_utc():
    # 17:30 a Londra in estate (BST, UTC+1) = 16:30 UTC = 18:30 in Italia
    assert parse_kickoff("22/08/2026", "17:30") == (datetime(2026, 8, 22, 16, 30, tzinfo=UTC), True)
    # 19:45 a Londra in inverno (GMT) = 19:45 UTC = 20:45 in Italia
    assert parse_kickoff("10/01/2027", "19:45") == (datetime(2027, 1, 10, 19, 45, tzinfo=UTC), True)


def test_date_without_time():
    assert parse_kickoff("25/08/12", None) == (datetime(2012, 8, 25, 12, 0, tzinfo=UTC), False)


def test_parse_recent_season():
    [m] = parse_csv(CSV_2026)
    assert (m.league, m.home, m.away) == ("I1", "Inter", "Monza")
    assert (m.home_goals, m.away_goals, m.ht_home_goals, m.ht_away_goals) == (4, 1, 1, 1)
    assert m.finished
    assert (m.home_xg, m.away_xg) == (Decimal("1.05"), Decimal("1.23"))
    assert m.stats["home_shots"] == 13 and m.stats["away_shots_on_target"] == 3 and m.stats["away_fouls"] == 14
    assert odds_of(m, "bet365", "1X2") == {"1": Decimal("1.2"), "X": Decimal("7"), "2": Decimal("13")}
    assert odds_of(m, "bet365", "1X2", closing=True) == {"1": Decimal("1.14"), "X": Decimal("8.5"), "2": Decimal("17")}
    assert odds_of(m, "betfair_ex", "1X2")["2"] == Decimal("17")
    assert odds_of(m, "market_avg", "OU2.5") == {"over": Decimal("1.58"), "under": Decimal("2.3")}
    assert odds_of(m, "pinnacle", "1X2") == {}


def test_parse_old_season_and_skip_empty_rows():
    [m] = parse_csv(CSV_2012)
    assert not m.kickoff_has_time
    assert m.home_xg is None
    assert odds_of(m, "pinnacle", "1X2") == {"1": Decimal("2.1"), "X": Decimal("3.32"), "2": Decimal("4.13")}
    assert odds_of(m, "pinnacle", "1X2", closing=True)["1"] == Decimal("1.97")
    # Senza colonne Max/Avg si usano quelle BetBrain
    assert odds_of(m, "market_max", "1X2") == {"1": Decimal("2.1"), "X": Decimal("3.33"), "2": Decimal("4.15")}
    assert odds_of(m, "market_avg", "OU2.5") == {"over": Decimal("2.2"), "under": Decimal("1.66")}


def test_fixture_has_no_result():
    napoli, beveren = parse_csv(FIXTURES)
    assert not napoli.finished and napoli.home_goals is None
    assert napoli.kickoff_at == datetime(2026, 10, 10, 18, 45, tzinfo=UTC)  # 19:45 BST = 20:45 in Italia
    assert beveren.league == "B1"


def test_incomplete_odds_are_ignored():
    text = "Div,Date,HomeTeam,AwayTeam,B365H,B365D,B365A\nI1,25/08/12,A,B,2.1,,3.5\n"
    [m] = parse_csv(text)
    assert m.odds == []
