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
