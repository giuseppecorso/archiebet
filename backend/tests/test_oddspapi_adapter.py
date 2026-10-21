"""Adapter OddsPapi: lettura delle risposte (struttura reale, ottobre 2026), budget del mese, pause."""

from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.cache import FileCache
from app.adapters.oddspapi import OddsPapiAdapter, OddsPapiError, QuotaExhausted, parse_current, parse_fixtures, parse_history, prices_at


def player(price, active=True):
    return {"players": {"0": {"active": active, "price": price, "playerName": None, "mainLine": True}}}


ODDS_BODY = [
    {
        "fixtureId": "id1", "participant1Id": 2701, "participant2Id": 2796, "tournamentId": 23, "statusId": 0,
        "startTime": "2026-10-16T18:30:00.000Z", "hasOdds": True,
        "bookmakerOdds": {
            "pinnacle": {"suspended": False, "markets": {
                "101": {"marketActive": True, "outcomes": {"101": player(2.05), "102": player(3.6), "103": player(3.94)}},
                "1010": {"marketActive": True, "outcomes": {"1010": player(1.95), "1011": player(1.9, active=False)}},
                "1012": {"marketActive": True, "outcomes": {"1012": player(3.2)}},  # Over 3.5: non lo usiamo
            }},
            "unknownbook": {"markets": {"101": {"outcomes": {"101": player(9.0)}}}},
        },
    }
]  # fmt: skip


def hist(*entries):
    return {"players": {"0": [{"createdAt": t, "price": p, "active": a, "limit": None} for t, p, a in entries]}}


HISTORY_BODY = {
    "fixtureId": "id1",
    "bookmakers": {
        "sisal.it": {"markets": {"101": {"outcomes": {
            # fuori ordine di proposito
            "101": hist(("2026-10-14T10:00:00.000Z", 2.45, True), ("2026-10-12T10:00:00.000Z", 2.40, True)),
            "102": hist(("2026-10-12T10:00:00.000Z", 3.6, True)),
            "103": hist(("2026-10-12T10:00:00.000Z", 2.7, True), ("2026-10-15T10:00:00.000Z", 2.9, False)),
        }}}},
    },
}  # fmt: skip


def test_parse_fixtures_and_current_prices():
    [fx] = parse_fixtures(ODDS_BODY)
    assert (fx.id, fx.tournament_id, fx.home_id, fx.away_id) == ("id1", 23, 2701, 2796)
    assert fx.start_time == datetime(2026, 10, 16, 18, 30, tzinfo=UTC)
    current = parse_current(ODDS_BODY)
    # Under non attivo → scartato; Over 3.5 e bookmaker sconosciuti ignorati
    assert current == {"id1": {"pinnacle": {"1X2": {"1": 2.05, "X": 3.6, "2": 3.94}, "OU2.5": {"over": 1.95}, "OU3.5": {"over": 3.2}}}}  # OU3.5 letta dal D130


def test_history_sorted_and_prices_at_a_moment():
    h = parse_history(HISTORY_BODY)
    assert [p for _, p in h["sisal"]["1X2"]["1"]] == [2.40, 2.45]  # in ordine di tempo, con il nome ArchieBet
    assert len(h["sisal"]["1X2"]["2"]) == 1  # il prezzo non attivo è scartato
    early = prices_at(h, datetime(2026, 10, 13, tzinfo=UTC))
    assert early == {"sisal": {"1X2": {"1": 2.40, "X": 3.6, "2": 2.7}}}
    later = prices_at(h, datetime(2026, 10, 16, tzinfo=UTC))
    assert later["sisal"]["1X2"]["1"] == 2.45
    assert prices_at(h, datetime(2026, 10, 1, tzinfo=UTC)) == {}  # prima della prima quota


class FakeHttp:
    def __init__(self, used=0, limit=250):
        self.calls: list[tuple[str, dict]] = []
        self.used, self.limit = used, limit

    def __call__(self, url, params):
        endpoint = url.rsplit("/", 1)[1]
        self.calls.append((endpoint, params))
        if endpoint == "account":
            return 200, {"subscriptions": [{"is_active": True, "request_limit": self.limit, "request_count": self.used}]}
        if endpoint == "odds-by-tournaments":
            if "bookmakers" in params:
                return 400, {"error": {"message": "Invalid number of bookmakers specified."}}
            return 200, ODDS_BODY
        if endpoint == "historical-odds":
            return 200, HISTORY_BODY
        return 200, {"2701": "Lazio Rome", "2796": "Inter Milano"}


def adapter(tmp_path, http, sleeps=None, reserve=20):
    clock = iter(range(0, 10_000, 1))
    return OddsPapiAdapter(
        FileCache(tmp_path, "oddspapi"), "KEY", http_get=http, monthly_reserve=reserve,
        sleep=(sleeps.append if sleeps is not None else lambda s: None), clock=lambda: float(next(clock)),
    )  # fmt: skip


def test_upcoming_uses_one_request_and_cache(tmp_path):
    http = FakeHttp()
    a = adapter(tmp_path, http)
    fixtures, current = a.upcoming(max_age=timedelta(hours=5))
    assert [f.id for f in fixtures] == ["id1"] * 4 and "pinnacle" in current["id1"]  # la finta risponde uguale
    # prima controlla il budget (gratis), poi una richiesta ogni 5 campionati con lo stesso bookmaker
    assert [c[0] for c in http.calls] == ["account"] + ["odds-by-tournaments"] * 4
    assert http.calls[1][1] == {"tournamentIds": "23,53,17,8,35", "bookmaker": "pinnacle", "apiKey": "KEY"}
    assert http.calls[2][1]["tournamentIds"] == "34,18,54,44,182"
    assert http.calls[3][1]["tournamentIds"] == "7,679,34480"  # coppe europee
    assert http.calls[4][1] == {"tournamentIds": "26554,26556,26558", "bookmaker": "sisal.it", "apiKey": "KEY"}  # Serie C
    assert a.remaining_month == 246
    a.upcoming(max_age=timedelta(hours=5))
    assert len(http.calls) == 5  # dalla cache


def test_listing_without_fixtures_is_empty_not_an_error(tmp_path):
    def answer(url, params):
        if url.endswith("account"):
            return 200, {"subscriptions": [{"is_active": True, "request_limit": 250, "request_count": 0}]}
        return 404, {"error": {"message": "No fixtures found for the specified tournament IDs and bookmaker."}}

    a = adapter(tmp_path, answer)
    assert a.upcoming(max_age=timedelta(hours=5)) == ([], {})


def test_monthly_reserve_blocks_paid_calls_but_not_free_ones(tmp_path):
    http = FakeHttp(used=230)
    a = adapter(tmp_path, http, reserve=20)
    with pytest.raises(QuotaExhausted):
        a.upcoming(max_age=timedelta(hours=5))
    assert a.history("id1", ["sisal.it"], max_age=timedelta(hours=1))["sisal"]  # lo storico è gratuito


def test_history_groups_three_bookmakers_and_waits_between_calls(tmp_path):
    http, sleeps = FakeHttp(), []
    a = adapter(tmp_path, http, sleeps)
    a.history("id1", ["sisal.it", "snai.it", "eurobet.it", "goldbet.it"], max_age=timedelta(hours=1))
    calls = [p["bookmakers"] for e, p in http.calls if e == "historical-odds"]
    assert calls == ["sisal.it,snai.it,eurobet.it", "goldbet.it"]
    assert sleeps and sleeps[0] == pytest.approx(5.5 - 1)  # 5 secondi e mezzo tra due chiamate allo storico



def test_history_without_odds_is_empty_not_an_error(tmp_path):
    def missing(url, params):
        return 404, {"error": {"message": "No historical odds found."}}

    a = adapter(tmp_path, missing, [])
    assert a.history("id1", ["sisal.it"], max_age=timedelta(hours=1)) == {}


def test_rate_limited_history_waits_and_retries(tmp_path):
    limited = (429, {"error": {"message": "You are being rate limited."}})
    answers = iter([limited, limited, (200, {"fixtureId": "id1", "bookmakers": {}})])
    sleeps = []
    a = adapter(tmp_path, lambda url, params: next(answers), sleeps)
    assert a.history("id1", ["sisal.it"], max_age=timedelta(hours=1)) == {}
    assert sleeps == [5.5, 11.0]  # attese crescenti

def test_errors_are_raised_and_not_cached(tmp_path):
    def broken(url, params):
        if url.endswith("account"):
            return 200, {"subscriptions": [{"is_active": True, "request_limit": 250, "request_count": 0}]}
        return 400, {"error": {"message": "Invalid parameter", "details": "bad"}}

    a = adapter(tmp_path, broken)
    with pytest.raises(OddsPapiError, match="Invalid parameter"):
        a.participants()
    assert a.remaining_month == 249  # anche gli errori consumano una richiesta
    assert not (tmp_path / "oddspapi").exists() or not any((tmp_path / "oddspapi").iterdir())


def test_http_get_retries_when_the_network_drops(monkeypatch):
    import httpx2

    from app.adapters import oddspapi

    class Ok:
        status_code = 200

        def json(self):
            return {"ok": True}

    answers = [httpx2.ConnectTimeout("handshake"), Ok()]

    def fake_get(*args, **kwargs):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(httpx2, "get", fake_get)
    waits = []
    assert oddspapi._http_get("https://x", {}, sleep=waits.append) == (200, {"ok": True})
    assert waits == [10]
