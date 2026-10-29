"""Archie tifoso (D101-D102): feed, fatti, giudizi, tetto di spesa, misura dello spostamento delle quote."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.adapters.cache import FileCache
from app.adapters.news import NewsAdapter, parse_rss
from app.ai.client import Ai, cost_usd
from app.ai.gateway import AIGateway, BudgetExceeded
from app.config import Settings
from app.ai.news import Extraction, Fact, Judgment
from app.ingest.news import fan_test, needs_judgment, run_news, signals, store_items
from app.models import Competition, Match, MatchInsight, MatchOdds, NewsItem, Team, TeamFact, UsageEvent

NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)

TUTTOC = """<?xml version="1.0"?><rss><channel>
<item><title>Picerno, esonerato De Luca</title><link>https://www.tuttoc.com/a</link>
<description>&lt;p&gt;Contro il Barletta &amp;egrave; arrivata la terza sconfitta&lt;/p&gt;</description>
<pubDate>Wed, 21 Oct 2026 08:40:22 +0200</pubDate></item>
<item><title>Vecchia notizia</title><link>https://www.tuttoc.com/old</link><description>x</description>
<pubDate>Wed, 01 Oct 2026 08:00:00 +0200</pubDate></item>
<item><title>Senza data</title><link>https://www.tuttoc.com/nodate</link></item>
</channel></rss>"""

GNEWS = """<?xml version="1.0"?><rss><channel>
<item><title>Catania, il caso Zago - Forzacatania</title><link>https://news.google.com/x</link>
<description>&lt;a href="https://news.google.com/x"&gt;link&lt;/a&gt;</description>
<pubDate>Mon, 19 Oct 2026 06:54:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_rss_cleans_text_and_skips_items_without_date():
    items = parse_rss(TUTTOC, "tuttoc")
    assert [i.url for i in items] == ["https://www.tuttoc.com/a", "https://www.tuttoc.com/old"]
    assert items[0].summary == "Contro il Barletta è arrivata la terza sconfitta"
    assert items[0].published_at == datetime(2026, 10, 21, 6, 40, 22, tzinfo=UTC)
    [g] = parse_rss(GNEWS, "gnews")
    assert g.summary == "" and g.title.startswith("Catania")  # Google News: solo il titolo


def test_store_items_keeps_recent_and_new_ones(db):
    items = parse_rss(TUTTOC, "tuttoc")
    assert store_items(db, items, NOW) == 1  # la vecchia (20 giorni) non si salva
    assert store_items(db, items, NOW) == 0  # già presente


class FakeClient:
    """Finto client Anthropic: restituisce le risposte in ordine e conta le chiamate."""

    def __init__(self, outputs, tokens=(1000, 200)):
        self.outputs, self.tokens, self.calls = list(outputs), tokens, []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(input_tokens=self.tokens[0], output_tokens=self.tokens[1], cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(usage=usage, stop_reason="end_turn", parsed_output=self.outputs.pop(0))


def test_budget_is_checked_before_every_call(db):
    assert cost_usd("claude-sonnet-5-5", 1_000_000, 100_000) == pytest.approx(2.0 + 1.0)
    settings = Settings(ai_monthly_budget_eur=10)
    db.add(UsageEvent(source="ai:x:sonnet-5-5", cost_eur=Decimal("9.99"), created_at=NOW - timedelta(days=1)))
    db.add(UsageEvent(source="ai:x:sonnet-5-5", cost_eur=Decimal(50), created_at=datetime(2026, 9, 30, tzinfo=UTC)))  # settembre: non conta
    db.commit()
    client = FakeClient([Judgment(side="none", strength="nessuna", reason="-")])
    ai = Ai(db, "k", settings, client=client, now=lambda: NOW)
    ai.parse("t", "claude-haiku-5-5", "s", "u", Judgment)  # 9,99 < 10: passa e registra il costo
    spent = AIGateway(db, settings).global_status(NOW).spent_eur
    assert float(spent) == pytest.approx(9.99 + cost_usd("claude-haiku-5-5", 1000, 200))
    assert db.query(UsageEvent).filter(UsageEvent.source == "ai:t:haiku-5-5").one().units == 1200
    db.add(UsageEvent(source="ai:x:sonnet-5-5", cost_eur=Decimal("0.02"), created_at=NOW))
    db.commit()
    with pytest.raises(BudgetExceeded):
        ai.parse("t", "claude-haiku-5-5", "s", "u", Judgment)
    assert len(client.calls) == 1


def setup_match(db):
    comp = Competition(code="ITA-C-C", name="Serie C C", country="Italia", tier=3)
    home, away = Team(name="Picerno", country="Italia"), Team(name="Barletta", country="Italia")
    db.add_all([comp, home, away])
    db.flush()
    m = Match(competition_id=comp.id, season="2026/27", kickoff_at=NOW + timedelta(days=2), kickoff_has_time=True, home_team_id=home.id, away_team_id=away.id)
    db.add(m)
    db.flush()
    for bm in ("sisal", "snai"):
        for sel, price in zip(("1", "X", "2"), ("2.00", "3.20", "4.00")):
            db.add(MatchOdds(match_id=m.id, source="oddspapi", bookmaker=bm, market="1X2", selection=sel, price=Decimal(price), is_closing=False))
    db.commit()
    return m


class FakeNews(NewsAdapter):
    def __init__(self):
        super().__init__(FileCache(__import__("pathlib").Path("."), "unused"))

    def tuttoc(self, max_age=None):
        return parse_rss(TUTTOC, "tuttoc")

    def google_news(self, team, max_age=None):
        raise TimeoutError("rete")  # un feed che non risponde non ferma il giro


def test_full_round_extracts_facts_judges_and_records_consensus(db):
    m = setup_match(db)
    facts = Extraction(facts=[
        Fact(item=1, team="Picerno", kind="allenatore_nuovo", player="Claudio De Luca", detail="Esonerato De Luca"),
        Fact(item=1, team="Juventus", kind="assente", player="X", detail="non è in lista"),  # scartato
        Fact(item=7, team="Picerno", kind="assente", player="Y", detail="notizia inesistente"),  # scartato
    ])  # fmt: skip
    judgment = Judgment(side="away", strength="netta", reason="Picerno senza allenatore")
    client = FakeClient([facts, judgment])
    ai = Ai(db, "k", Settings(ai_monthly_budget_eur=10), client=client, now=lambda: NOW)
    report = run_news(db, FakeNews(), ai, "claude-haiku-5-5", "claude-sonnet-5-5", NOW)
    assert (report.new, report.processed, report.facts, report.judged) == (1, 1, 1, 1)
    assert len(report.errors) == 2  # Google News di Picerno e Barletta
    [fact] = db.query(TeamFact).all()
    assert (fact.kind, fact.player) == ("allenatore_nuovo", "Claudio De Luca")
    [insight] = db.query(MatchInsight).all()
    assert (insight.side, insight.strength) == ("away", "netta")
    assert insight.p_away == pytest.approx((1 / 4.0) / (1 / 2.0 + 1 / 3.2 + 1 / 4.0))
    assert db.query(NewsItem).one().processed_at is not None
    # Secondo giro subito dopo: niente notizie nuove, niente nuove chiamate
    run_news(db, FakeNews(), ai, "claude-haiku-5-5", "claude-sonnet-5-5", NOW + timedelta(hours=1))
    assert len(client.calls) == 2


def test_needs_judgment_only_with_new_facts_every_12_hours():
    fact = SimpleNamespace(created_at=NOW)
    last = SimpleNamespace(created_at=NOW - timedelta(hours=13))
    assert not needs_judgment(None, [], NOW)
    assert needs_judgment(None, [fact], NOW)
    assert needs_judgment(last, [fact], NOW)
    assert not needs_judgment(SimpleNamespace(created_at=NOW - timedelta(hours=2)), [fact], NOW)  # troppo presto
    assert not needs_judgment(last, [SimpleNamespace(created_at=NOW - timedelta(days=1))], NOW)  # niente di nuovo


def insight(match_id, at, side, p=(0.5, 0.3, 0.2), close=(0.45, 0.3, 0.25), strength="lieve"):
    return MatchInsight(match_id=match_id, created_at=at, side=side, strength=strength, reason="", facts=1,
                        p_home=p[0], p_draw=p[1], p_away=p[2], close_home=close[0], close_draw=close[1], close_away=close[2])  # fmt: skip


def test_signal_is_the_first_judgment_with_a_side_at_least_30_minutes_before():
    ko = NOW + timedelta(days=1)
    rows = [
        (insight(1, NOW, "none"), ko),
        (insight(1, NOW + timedelta(hours=1), "away"), ko),  # il segnale: +5 punti verso l'ospite
        (insight(1, NOW + timedelta(hours=13), "home"), ko),  # dopo: non conta
        (insight(2, ko - timedelta(minutes=10), "home"), ko),  # troppo tardi
        (insight(3, NOW, "home", p=(None, None, None)), ko),  # senza quote al momento: escluso, non sostituito
        (insight(3, NOW + timedelta(hours=2), "home"), ko),
    ]
    [s] = signals(rows)
    assert (s.match_id, s.side) == (1, "away") and s.move == pytest.approx(0.05)


def test_fan_test_on_the_database(db):
    m = setup_match(db)
    db.add(insight(m.id, NOW, "home"))
    db.commit()
    found, est = fan_test(db)
    assert len(found) == 1 and est is None  # servono almeno 2 segnali per un errore standard


def test_match_fan_endpoint(logged_client, db):
    m = setup_match(db)
    news = NewsItem(source="tuttoc", url="https://www.tuttoc.com/a", title="t", summary="", published_at=NOW, fetched_at=NOW)
    db.add(news)
    db.flush()
    db.add(TeamFact(team_id=m.home_team_id, news_id=news.id, kind="squalifica", player="Rossi", detail="Squalificato per un turno",
                    published_at=NOW, created_at=NOW))  # fmt: skip
    db.add(insight(m.id, NOW, "away", strength="netta"))
    db.commit()
    body = logged_client.get(f"/api/fan/match/{m.id}").json()
    [fact] = body["facts"]
    assert (fact["label"], fact["player"], fact["url"]) == ("Squalifica", "Rossi", "https://www.tuttoc.com/a")
    assert body["insight"]["side"] == "away" and body["test"]["target"] == 150
    assert logged_client.get("/api/fan/match/9999").status_code == 404


def test_no_judgment_without_odds(db):
    m = setup_match(db)
    db.query(MatchOdds).delete()
    db.commit()
    client = FakeClient([Extraction(facts=[Fact(item=1, team="Picerno", kind="squalifica", player="Rossi", detail="fuori un turno")])])
    report = run_news(db, FakeNews(), Ai(db, "k", Settings(ai_monthly_budget_eur=10), client=client, now=lambda: NOW),
                      "claude-haiku-5-5", "claude-opus-5-5", NOW)  # fmt: skip
    assert report.facts == 1 and report.judged == 0 and len(client.calls) == 1  # i fatti sì, il giudizio aspetta le quote


def test_google_news_query_is_targeted_and_polite(tmp_path):
    urls, pauses = [], []
    adapter = NewsAdapter(FileCache(tmp_path, "news"), http_get=lambda url: urls.append(url) or GNEWS, sleep=pauses.append)
    adapter.google_news("Torino")
    adapter.google_news("Monza")
    adapter.google_news("Torino")  # in cache: nessuna nuova ricerca
    assert len(urls) == 2 and pauses == [1.5]  # pausa tra due ricerche vere
    assert "infortunio" in urls[0] and "%22Torino%22" in urls[0]


def test_fan_test_keeps_serie_c_and_serie_a_b_apart(db):
    c_match = setup_match(db)  # Serie C
    comp_a = Competition(code="ITA-A", name="Serie A", country="Italia", tier=1)
    db.add(comp_a)
    db.flush()
    a_match = Match(competition_id=comp_a.id, season="2026/27", kickoff_at=NOW + timedelta(days=2), kickoff_has_time=True,
                    home_team_id=c_match.home_team_id, away_team_id=c_match.away_team_id)  # fmt: skip
    db.add(a_match)
    db.flush()
    db.add_all([insight(c_match.id, NOW, "home"), insight(a_match.id, NOW, "away")])
    db.commit()
    c_signals, _ = fan_test(db, serie_c=True)
    ab_signals, _ = fan_test(db, serie_c=False)
    assert [s.match_id for s in c_signals] == [c_match.id] and [s.match_id for s in ab_signals] == [a_match.id]


def test_match_picks_and_analysis_endpoints(logged_client, db, monkeypatch):
    from app.ai import analysis as analysis_module
    from app.ai.analysis import Analysis
    from app.api import fan as fan_api

    m = setup_match(db)
    m.kickoff_at = datetime.now(UTC) + timedelta(days=2)
    db.commit()
    picks = logged_client.get(f"/api/picks/match/{m.id}").json()
    assert [p["market"] for p in picks["markets"]] == ["1X2", "DC", "DNB"]  # dal consenso di Sisal e Snai (Draw No Bet dall'1X2, D135)
    assert [(s["kind"], s["offer"]["verdict"]) for s in picks["suggestions"]] == [("sicuro", "paga poco")]  # il più probabile tra 2 e 4 è lo stesso: non si ripete

    brief = fan_api.analysis_brief(db, m)
    assert "Picerno (casa) - Barletta (ospite)" in brief and "Pronostico più sicuro" in brief
    calls = []

    def fake_write(ai, model, text):
        calls.append(text)
        return Analysis(summary="Partita equilibrata.", points=["Uno", "Due"], verdict="Il sicuro è il 1X.")

    monkeypatch.setattr(analysis_module, "write_analysis", fake_write)
    monkeypatch.setattr(fan_api, "get_settings", lambda: Settings(anthropic_api_key="k"))
    assert logged_client.get(f"/api/fan/match/{m.id}/analysis").json() is None
    first = logged_client.post(f"/api/fan/match/{m.id}/analysis").json()
    assert first["points"] == ["Uno", "Due"] and len(calls) == 1
    logged_client.post(f"/api/fan/match/{m.id}/analysis")  # ancora fresca: nessuna nuova chiamata
    assert len(calls) == 1
    assert logged_client.get(f"/api/fan/match/{m.id}/analysis").json()["summary"] == "Partita equilibrata."


def test_speculative_headlines_cannot_sack_a_coach():
    from app.ai.news import guarded_kind

    assert guarded_kind("allenatore_nuovo", "Sarri esonero Atalanta nuove quote: salta un'altra panchina in A?") == "allenatore_in_bilico"
    assert guarded_kind("allenatore_nuovo", "Atalanta, ufficiale: esonerato Sarri") == "allenatore_nuovo"
    assert guarded_kind("assente", "Scamacca out, a rischio la sfida con la Fiorentina") == "assente"


def test_confirmed_sackings_stay_facts_even_with_a_question():
    from app.ai.news import guarded_kind

    assert guarded_kind("allenatore_nuovo", "Qui Picerno, esonerato De Luca: con la Salernitana tocca a un ex granata?") == "allenatore_nuovo"
    assert guarded_kind("allenatore_nuovo", "Sampdoria, accordo vicino con D'Angelo: firma a un passo?") == "allenatore_in_bilico"


def test_player_facts_must_match_the_squad():
    from app.ingest.news import name_tokens, plays_for

    squads = {1: name_tokens("D. Vlahović") | name_tokens("Moise Kean"), 2: name_tokens("Paulo Dybala"), 3: name_tokens("Lautaro Martínez")}
    assert not plays_for(squads, 1, "assente", "Dybala")  # gioca nella Roma, non nella Fiorentina
    assert plays_for(squads, 1, "assente", "Kean")
    assert plays_for(squads, 3, "assente", "Lautaro")  # il nome di battesimo basta
    assert plays_for(squads, 1, "assente", "Kvaratskhelia")  # sconosciuto (infortunato lungo, altra lega): si tiene
    assert plays_for(squads, 1, "squalifica", "Allegri")  # allenatore: non è in nessuna rosa, si tiene
    assert plays_for(squads, 9, "assente", "Mario Rossi")  # squadra senza rosa (Serie C): si tiene
