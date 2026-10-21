"""Fonte dati OddsPapi (api.oddspapi.io/v4): quote dei bookmaker italiani e di Pinnacle (D61).

Verificato sulle risposte reali (ottobre 2026):
- chiave nel parametro "apiKey"; /account non consuma richieste e dice quante ne restano nel mese
- piano free: 250 richieste al mese; contano anche le risposte di errore (4xx)
- /odds-by-tournaments accetta UN solo bookmaker per chiamata (parametro "bookmaker", la documentazione dice 3)
  e al massimo 5 campionati (non documentato)
- /historical-odds è gratuito (non conta nel mese): fino a 3 bookmaker per chiamata, 5 secondi di pausa,
  funziona anche per le partite future; betfair-ex solo da solo e con un esito, quindi non lo usiamo
- id: Serie A 23, Serie B 53, Premier League 17, LaLiga 8, Bundesliga 35, Ligue 1 34
  (Serie C gironi 26554/26556/26558); mercati 101 = 1X2 (esiti 101/102/103),
  1010 = Under/Over 2.5 (esiti 1010 over / 1011 under), 101902 = doppia chance (1X / 12 / 2X), 104 = Goal/NoGoal
- le squadre arrivano solo come id: i nomi si prendono da /participants (una richiesta, poi in cache)
"""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.adapters.base import DataSourceAdapter
from app.adapters.cache import FileCache

# La chiave viaggia nell'indirizzo: la libreria HTTP lo scriverebbe nel log a ogni richiesta
logging.getLogger("httpx2").setLevel(logging.WARNING)

SOURCE = "oddspapi"
BASE_URL = "https://api.oddspapi.io/v4"
SOCCER = 10

TOURNAMENTS = {
    23: "ITA-A", 53: "ITA-B", 17: "ENG-1", 8: "ESP-1", 35: "GER-1",
    34: "FRA-1", 18: "ENG-2", 54: "ESP-2", 44: "GER-2", 182: "FRA-2",  # seconde divisioni (D75)
    7: "EU-CL", 679: "EU-EL", 34480: "EU-ECL",  # coppe europee (D85, id verificati con /tournaments)
    26554: "ITA-C-A", 26556: "ITA-C-B", 26558: "ITA-C-C",  # Serie C (D88): Pinnacle non la quota, Sisal sì
}  # fmt: skip

# slug OddsPapi → nome del bookmaker in ArchieBet
SHARP = {"pinnacle": "pinnacle"}
ITALIAN = {
    "sisal.it": "sisal",
    "snai.it": "snai",
    "eurobet.it": "eurobet",
    "goldbet.it": "goldbet",
    "lottomatica.it": "lottomatica",
    "betflag.it": "betflag",
    "bet365.it": "bet365_it",
    "planetwin365.it": "planetwin365",
    "betsson.it": "betsson",
}
BOOKMAKERS = SHARP | ITALIAN

# id mercato → (mercato in ArchieBet, id esito → esito)
MARKETS = {
    "101": ("1X2", {"101": "1", "102": "X", "103": "2"}),
    "1010": ("OU2.5", {"1010": "over", "1011": "under"}),
    "108": ("OU1.5", {"108": "over", "109": "under"}),  # D130: solo Pronostici, multipla e schedina, non il radar
    "1012": ("OU3.5", {"1012": "over", "1013": "under"}),
    "106": ("OU0.5", {"106": "over", "107": "under"}),  # D131 (esiti verificati sulle definizioni dei mercati)
    "1014": ("OU4.5", {"1014": "over", "1015": "under"}),
    "101902": ("DC", {"101902": "1X", "101903": "12", "101904": "X2"}),  # Pinnacle non la quota
    "104": ("GG", {"104": "yes", "105": "no"}),
}

# Pausa minima tra due chiamate allo stesso endpoint (secondi), con un po' di margine
COOLDOWN = {"odds-by-tournaments": 1.5, "historical-odds": 5.5, "participants": 1.5, "account": 1.5, "fixtures": 2.0, "markets": 1.5}
FREE_ENDPOINTS = {"historical-odds", "account"}
MAX_BOOKMAKERS_PER_HISTORY_CALL = 3
RATE_LIMIT_RETRIES = 4
MAX_TOURNAMENTS_PER_CALL = 5
# Con quale bookmaker chiedere l'elenco partite: Pinnacle dove c'è, altrimenti un bookmaker italiano (D88)
LISTING_BOOKMAKER = {26554: "sisal.it", 26556: "sisal.it", 26558: "sisal.it"}

Prices = dict[str, dict[str, dict[str, float]]]  # bookmaker → mercato → esito → quota
History = dict[str, dict[str, dict[str, list[tuple[datetime, float]]]]]  # bookmaker → mercato → esito → [(ora, quota)]


class OddsPapiError(Exception):
    """Errore restituito dal servizio. Non viene mai salvato in cache."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class QuotaExhausted(OddsPapiError):
    """Richieste del mese quasi finite: ci fermiamo per lasciare una riserva."""


@dataclass(frozen=True)
class OPFixture:
    id: str
    tournament_id: int
    start_time: datetime
    home_id: int
    away_id: int
    status_id: int


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse_fixtures(body: list[dict[str, Any]]) -> list[OPFixture]:
    return [
        OPFixture(f["fixtureId"], f["tournamentId"], _time(f["startTime"]), f["participant1Id"], f["participant2Id"], f["statusId"])
        for f in body
    ]


def parse_current(body: list[dict[str, Any]]) -> dict[str, Prices]:
    """Quote attuali (prezzi attivi) di ogni partita da /odds-by-tournaments, solo per i mercati che usiamo."""
    out: dict[str, Prices] = {}
    for f in body:
        for slug, book in (f.get("bookmakerOdds") or {}).items():
            if slug not in BOOKMAKERS or book.get("suspended"):
                continue
            for market_id, market in (book.get("markets") or {}).items():
                if market_id not in MARKETS or not market.get("marketActive", True):
                    continue
                name, outcomes = MARKETS[market_id]
                for outcome_id, outcome in (market.get("outcomes") or {}).items():
                    entry = (outcome.get("players") or {}).get("0")
                    if outcome_id in outcomes and entry and entry.get("active") and entry.get("price"):
                        out.setdefault(f["fixtureId"], {}).setdefault(BOOKMAKERS[slug], {}).setdefault(name, {})[outcomes[outcome_id]] = float(entry["price"])
    return out


# Angoli e cartellini (D94): solo il riferimento e i bookmaker di Giuse, per non moltiplicare le righe nel database
SECONDARY_SLUGS = {"pinnacle", "sisal.it", "eurobet.it"}


def secondary_market_map(definitions: Sequence[dict[str, Any]]) -> dict[str, tuple[str, dict[str, str]]]:
    """Over/Under .5 di angoli e cartellini a fine partita (totali e per squadra) → nome nel radar ("COR9.5", "CRDH1.5", ...)."""
    out = {}
    for d in definitions:
        name, line = d.get("marketName", ""), float(d.get("handicap") or 0)
        if d.get("period") != "fulltime" or "Half" in name or "Over Under" not in name or line % 1 != 0.5:
            continue
        family = "COR" if name.startswith("Corners") else "CRD" if name.startswith("Bookings") else None
        if family is None:
            continue
        side = "H" if "Team 1" in name else "A" if "Team 2" in name else ""
        outcomes = {str(o["outcomeId"]): o["outcomeName"].lower() for o in d.get("outcomes", []) if o["outcomeName"].lower() in ("over", "under")}
        if len(outcomes) == 2:
            out[str(d["marketId"])] = (f"{family}{side}{line:.1f}", outcomes)
    return out


def parse_history(body: dict[str, Any], secondary: dict[str, tuple[str, dict[str, str]]] | None = None) -> History:
    """Storia dei prezzi da /historical-odds, in ordine di tempo (la risposta non garantisce l'ordine)."""
    out: History = {}
    for slug, book in (body.get("bookmakers") or {}).items():
        if slug not in BOOKMAKERS:
            continue
        markets = {**MARKETS, **(secondary or {})} if slug in SECONDARY_SLUGS else MARKETS
        for market_id, market in (book.get("markets") or {}).items():
            if market_id not in markets:
                continue
            name, outcomes = markets[market_id]
            for outcome_id, outcome in (market.get("outcomes") or {}).items():
                entries = (outcome.get("players") or {}).get("0") or []
                if outcome_id not in outcomes:
                    continue
                points = sorted(
                    (_time(e["createdAt"]), float(e["price"])) for e in entries if e.get("active") and e.get("price")
                )
                if points:
                    out.setdefault(BOOKMAKERS[slug], {}).setdefault(name, {})[outcomes[outcome_id]] = points
    return out


def prices_at(history: History, at: datetime) -> Prices:
    """Le quote valide in un certo momento: per ogni esito l'ultimo prezzo registrato non dopo `at`.

    Con at = adesso sono le quote attuali; con at = calcio d'inizio sono le quote di chiusura.
    """
    out: Prices = {}
    for bookmaker, markets in history.items():
        for market, outcomes in markets.items():
            for selection, points in outcomes.items():
                before = [price for when, price in points if when <= at]
                if before:
                    out.setdefault(bookmaker, {}).setdefault(market, {})[selection] = before[-1]
    return out


class OddsPapiAdapter(DataSourceAdapter):
    source = SOURCE

    def __init__(
        self,
        cache: FileCache,
        api_key: str,
        on_call: Callable[[str], None] | None = None,
        http_get: Callable[..., Any] | None = None,
        monthly_reserve: int = 20,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        super().__init__(cache, on_call)
        self._api_key = api_key
        self._http_get = http_get or _http_get
        self._monthly_reserve = monthly_reserve
        self._sleep = sleep
        self._clock = clock
        self._last_call: dict[str, float] = {}
        self._secondary: dict[str, tuple[str, dict[str, str]]] | None = None
        self.remaining_month: int | None = None

    def _request(self, endpoint: str, params: dict[str, Any]) -> Any:
        if endpoint not in FREE_ENDPOINTS:
            if self.remaining_month is None:
                self.account()
            if self.remaining_month is not None and self.remaining_month <= self._monthly_reserve:
                raise QuotaExhausted(f"Restano {self.remaining_month} richieste nel mese: tengo la riserva di {self._monthly_reserve}")
        last = self._last_call.get(endpoint)
        if last is not None:
            wait = COOLDOWN.get(endpoint, 2.0) - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        status, body = self._http_get(f"{BASE_URL}/{endpoint}", {**params, "apiKey": self._api_key})
        for attempt in range(RATE_LIMIT_RETRIES):
            if status != 429 or endpoint not in FREE_ENDPOINTS:
                break
            # troppo veloci (es. aggiornamento e archivio insieme): attendo quanto chiede OddsPapi e riprovo
            self._sleep(_retry_after(body, COOLDOWN.get(endpoint, 5.5)) * (attempt + 1))
            status, body = self._http_get(f"{BASE_URL}/{endpoint}", {**params, "apiKey": self._api_key})
        self._last_call[endpoint] = self._clock()
        if endpoint not in FREE_ENDPOINTS and self.remaining_month is not None:
            self.remaining_month -= 1  # conta anche se la risposta è un errore
        if status != 200:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = f"HTTP {status} da {endpoint}: {error.get('message', '')} {error.get('details', '')}".strip()
            raise OddsPapiError(message, status)
        return body

    def account(self) -> dict[str, Any]:
        """Piano e richieste usate nel mese (chiamata gratuita, mai in cache)."""
        body = self._request("account", {})
        sub = next((s for s in body.get("subscriptions", []) if s.get("is_active")), None)
        if sub is not None:
            self.remaining_month = int(sub["request_limit"]) - int(sub["request_count"])
        return body

    def participants(self, max_age: timedelta = timedelta(days=30)) -> dict[str, str]:
        """id squadra → nome (tutto il calcio, una sola richiesta)."""
        return self.cached("participants?sportId=10", max_age, lambda: self._request("participants", {"sportId": SOCCER}))

    def upcoming(self, max_age: timedelta) -> tuple[list[OPFixture], dict[str, Prices]]:
        """Partite in programma di tutti i campionati seguiti con le quote di Pinnacle (Sisal per la Serie C).

        Una richiesta ogni 5 campionati con lo stesso bookmaker. Se in quei campionati non c'è nessuna partita quotata
        (pause, fine stagione) OddsPapi risponde 404: si salva un elenco vuoto, non è un guasto.
        """
        groups: dict[str, list[int]] = {}
        for t in TOURNAMENTS:
            groups.setdefault(LISTING_BOOKMAKER.get(t, "pinnacle"), []).append(t)
        body: list[dict[str, Any]] = []
        for bookmaker, tournaments in groups.items():
            for start in range(0, len(tournaments), MAX_TOURNAMENTS_PER_CALL):
                ids = ",".join(str(t) for t in tournaments[start : start + MAX_TOURNAMENTS_PER_CALL])
                params = {"tournamentIds": ids, "bookmaker": bookmaker}
                body += self.cached(f"odds-by-tournaments?tournamentIds={ids}&bookmaker={bookmaker}", max_age,
                                    lambda params=params: self._listing(params))
        return parse_fixtures(body), parse_current(body)

    def _listing(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self._request("odds-by-tournaments", params)
        except OddsPapiError as error:
            if error.status == 404:
                return []
            raise

    def markets(self, max_age: timedelta = timedelta(days=90)) -> list[dict[str, Any]]:
        """Definizioni di tutti i mercati del calcio (nome, linea, tempo, esiti): una richiesta ogni 3 mesi."""
        return self.cached(f"markets?sportId={SOCCER}", max_age, lambda: self._request("markets", {"sportId": SOCCER}))

    def finished_fixtures(self, tournament_id: int, max_age: timedelta) -> list[dict[str, Any]]:
        """Partite finite di un campionato (circa due stagioni): una richiesta."""
        params = {"tournamentId": tournament_id, "statusId": 2}
        return self.cached(f"fixtures?tournamentId={tournament_id}&statusId=2", max_age, lambda: self._request("fixtures", params))

    def secondary_markets(self) -> dict[str, tuple[str, dict[str, str]]]:
        """Mercati di angoli e cartellini dalle definizioni OddsPapi (in cache 3 mesi); vuoto se non disponibili."""
        if self._secondary is None:
            # Solo dalla cache: le definizioni le scarica l'aggiornamento normale (una richiesta ogni 3 mesi)
            definitions = self.cache.get(f"markets?sportId={SOCCER}", timedelta(days=90))
            self._secondary = secondary_market_map(definitions) if isinstance(definitions, list) else {}
        return self._secondary

    def raw_history(self, fixture_id: str, slugs: Sequence[str]) -> dict[str, Any] | None:
        """Storico completo di una partita (tutti i mercati, senza cache: è grande); None se OddsPapi non ce l'ha."""
        try:
            return self._request("historical-odds", {"fixtureId": fixture_id, "bookmakers": ",".join(slugs)})
        except OddsPapiError as error:
            if error.status == 404:
                return None
            raise

    def history(self, fixture_id: str, slugs: Sequence[str], max_age: timedelta) -> History:
        """Storia dei prezzi di una partita per più bookmaker (chiamate gratuite, 3 bookmaker per volta)."""
        out: History = {}
        for start in range(0, len(slugs), MAX_BOOKMAKERS_PER_HISTORY_CALL):
            group = ",".join(slugs[start : start + MAX_BOOKMAKERS_PER_HISTORY_CALL])
            params = {"fixtureId": fixture_id, "bookmakers": group}
            try:
                body = self.cached(f"historical-odds?fixtureId={fixture_id}&bookmakers={group}", max_age,
                                   lambda params=params: self._request("historical-odds", params))
            except OddsPapiError as error:
                if error.status != 404:
                    raise
                continue  # nessuna quota di questi bookmaker per la partita: non è un guasto
            out |= parse_history(body, self.secondary_markets())
        return out


def _retry_after(body: Any, default: float) -> float:
    """Secondi da aspettare secondo il messaggio di OddsPapi ("Please wait 1.49 seconds ..."), almeno default."""
    import re

    message = body.get("error", {}).get("message", "") if isinstance(body, dict) else ""
    found = re.search(r"wait ([0-9.]+) seconds", message)
    return max(default, float(found.group(1)) + 0.5) if found else default


def _http_get(url: str, params: dict[str, Any], attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> tuple[int, Any]:
    """GET con nuovi tentativi se la rete cade (timeout, connessione): i dati di OddsPapi arrivano a volte lenti."""
    import httpx2

    for attempt in range(attempts):
        try:
            response = httpx2.get(url, params=params, timeout=60, headers={"User-Agent": "ArchieBet/0.1 (uso personale)"})
            break
        except httpx2.TransportError:
            if attempt == attempts - 1:
                raise
            sleep(10 * (attempt + 1))
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {}
