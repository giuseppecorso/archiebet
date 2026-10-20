"""Fonte dati football-data.co.uk: storico risultati, statistiche e quote (Serie A e B, Premier League, LaLiga, Bundesliga, Ligue 1).

Formato verificato sui file reali (ottobre 2026):
- URL: https://football-data.co.uk/mmz4281/<stagione>/<lega>.csv, es. 2526/I1.csv; prossime partite in /fixtures.csv
- Date "dd/mm/yy" (stagioni vecchie) o "dd/mm/yyyy"; Time in ora inglese (Europe/London), assente prima del 2019/20
- Pinnacle presente fino al 2025/26, Betfair Exchange dal 2024/25, xG (HxG/AxG) dal 2026/27
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.adapters.base import DataSourceAdapter

SOURCE = "football-data"
BASE_URL = "https://football-data.co.uk"
UK_TZ = ZoneInfo("Europe/London")

# Codice della lega su football-data → codice del campionato in ArchieBet
LEAGUES = {
    "I1": "ITA-A", "I2": "ITA-B",
    "E0": "ENG-1", "SP1": "ESP-1", "D1": "GER-1", "F1": "FRA-1",
    "E1": "ENG-2", "SP2": "ESP-2", "D2": "GER-2", "F2": "FRA-2",  # seconde divisioni (D75)
}  # fmt: skip
FIRST_SEASON = 2005  # 2005/06: abbastanza storia per modello e backtest

# (bookmaker, chiusura?, prefissi colonne 1X2, prefissi colonne Over/Under 2.5), in ordine di preferenza
ODDS_COLUMNS: list[tuple[str, bool, list[str], list[str]]] = [
    ("pinnacle", False, ["PS", "P"], ["P"]),
    ("pinnacle", True, ["PSC"], ["PC"]),
    ("bet365", False, ["B365"], ["B365"]),
    ("bet365", True, ["B365C"], ["B365C"]),
    ("betfair_ex", False, ["BFE"], ["BFE"]),
    ("betfair_ex", True, ["BFEC"], ["BFEC"]),
    ("market_max", False, ["Max", "BbMx"], ["Max", "BbMx"]),
    ("market_max", True, ["MaxC"], ["MaxC"]),
    ("market_avg", False, ["Avg", "BbAv"], ["Avg", "BbAv"]),
    ("market_avg", True, ["AvgC"], ["AvgC"]),
]


def season_code(start_year: int) -> str:
    """2025 → "2526" (formato degli URL di football-data)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_label(start_year: int) -> str:
    """2025 → "2025/26" (formato usato in ArchieBet)."""
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def season_of(day: date) -> int:
    """Anno di inizio della stagione che contiene quel giorno (le stagioni partono a luglio)."""
    return day.year if day.month >= 7 else day.year - 1


@dataclass(frozen=True)
class OddsQuote:
    bookmaker: str
    market: str
    selection: str
    price: Decimal
    is_closing: bool


@dataclass
class FDMatch:
    league: str
    kickoff_at: datetime
    kickoff_has_time: bool
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    ht_home_goals: int | None = None
    ht_away_goals: int | None = None
    home_xg: Decimal | None = None
    away_xg: Decimal | None = None
    stats: dict[str, int | None] = field(default_factory=dict)
    referee: str | None = None
    odds: list[OddsQuote] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None


# Colonna football-data → campo di Match
STAT_COLUMNS = {
    "HS": "home_shots", "AS": "away_shots",
    "HST": "home_shots_on_target", "AST": "away_shots_on_target",
    "HC": "home_corners", "AC": "away_corners",
    "HF": "home_fouls", "AF": "away_fouls",
    "HY": "home_yellow", "AY": "away_yellow",
    "HR": "home_red", "AR": "away_red",
}  # fmt: skip


def _int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _decimal(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _price(value: str | None) -> Decimal | None:
    """Una quota valida è un numero maggiore di 1."""
    price = _decimal(value)
    return price if price is not None and price > 1 else None


def parse_kickoff(day: str, clock: str | None) -> tuple[datetime, bool]:
    """Data e ora di football-data (ora inglese) → istante UTC. Senza ora: mezzogiorno UTC del giorno."""
    fmt = "%d/%m/%Y" if len(day.strip().split("/")[-1]) == 4 else "%d/%m/%y"
    match_day = datetime.strptime(day.strip(), fmt).date()
    if clock and clock.strip():
        local = datetime.combine(match_day, time.fromisoformat(clock.strip()), tzinfo=UK_TZ)
        return local.astimezone(UTC), True
    return datetime.combine(match_day, time(12, 0), tzinfo=UTC), False


def _odds(row: dict[str, str]) -> list[OddsQuote]:
    quotes: list[OddsQuote] = []
    for bookmaker, closing, prefixes_1x2, prefixes_ou in ODDS_COLUMNS:
        for prefix in prefixes_1x2:
            prices = [_price(row.get(f"{prefix}{suffix}")) for suffix in "HDA"]
            if all(prices):
                quotes += [
                    OddsQuote(bookmaker, "1X2", selection, price, closing)
                    for selection, price in zip(("1", "X", "2"), prices, strict=True)
                ]
                break
        for prefix in prefixes_ou:
            over, under = _price(row.get(f"{prefix}>2.5")), _price(row.get(f"{prefix}<2.5"))
            if over and under:
                quotes += [
                    OddsQuote(bookmaker, "OU2.5", "over", over, closing),
                    OddsQuote(bookmaker, "OU2.5", "under", under, closing),
                ]
                break
    return quotes


def parse_csv(text: str) -> list[FDMatch]:
    """Testo di un CSV di football-data → partite. Le righe vuote o incomplete vengono saltate."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    matches: list[FDMatch] = []
    for row in reader:
        league, home, away, day = (row.get(k, "").strip() for k in ("Div", "HomeTeam", "AwayTeam", "Date"))
        if not (league and home and away and day):
            continue
        kickoff_at, has_time = parse_kickoff(day, row.get("Time"))
        matches.append(
            FDMatch(
                league=league,
                kickoff_at=kickoff_at,
                kickoff_has_time=has_time,
                home=home,
                away=away,
                home_goals=_int(row.get("FTHG") or row.get("HG")),
                away_goals=_int(row.get("FTAG") or row.get("AG")),
                ht_home_goals=_int(row.get("HTHG")),
                ht_away_goals=_int(row.get("HTAG")),
                home_xg=_decimal(row.get("HxG")),
                away_xg=_decimal(row.get("AxG")),
                stats={name: _int(row.get(column)) for column, name in STAT_COLUMNS.items()},
                referee=(row.get("Referee") or "").strip() or None,
                odds=_odds(row),
            )
        )
    return matches


class FootballDataAdapter(DataSourceAdapter):
    source = SOURCE

    def __init__(self, cache, on_call=None, http_get=None):
        super().__init__(cache, on_call)
        self._http_get = http_get or _download

    def season(self, league: str, start_year: int, current_season: int) -> list[FDMatch]:
        # Stagioni concluse: non cambiano più, la cache vale per sempre. Stagione in corso: 6 ore.
        max_age = timedelta(hours=6) if start_year >= current_season else timedelta(days=36500)
        url = f"{BASE_URL}/mmz4281/{season_code(start_year)}/{league}.csv"
        return parse_csv(self.cached(url, max_age, lambda: self._http_get(url)))

    def fixtures(self) -> list[FDMatch]:
        url = f"{BASE_URL}/fixtures.csv"
        return [m for m in parse_csv(self.cached(url, timedelta(hours=6), lambda: self._http_get(url))) if m.league in LEAGUES]


def _download(url: str) -> str:
    import httpx2

    response = httpx2.get(url, follow_redirects=True, timeout=30, headers={"User-Agent": "ArchieBet/0.1 (uso personale)"})
    response.raise_for_status()
    try:
        return response.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return response.content.decode("cp1252")  # alcuni file storici non sono in UTF-8
