"""Chiedi ad Archie (Fase 6): ciclo con gli strumenti, storico, tetto di spesa."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.ai.ask import Tool, ask
from app.ai.client import Ai, AiError
from app.config import Settings
from app.models import Competition, Match, Team, UsageEvent

USAGE = SimpleNamespace(input_tokens=500, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def tool_call(name, args, call_id="t1"):
    return SimpleNamespace(stop_reason="tool_use", usage=USAGE, content=[SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)])


def text(t):
    return SimpleNamespace(stop_reason="end_turn", usage=USAGE, content=[SimpleNamespace(type="text", text=t)])


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_ask_runs_tools_and_returns_the_text(db):
    seen = []
    tools = [Tool("cerca_partite", "Trova", {"squadra": "Nome"}, lambda squadra: seen.append(squadra) or "id 7 Bari - Catania")]
    client = FakeClient([tool_call("cerca_partite", {"squadra": "Bari"}), text("Il Bari gioca venerdì.")])
    ai = Ai(db, "k", Settings(ai_monthly_budget_eur=10), client=client)
    assert ask(ai, "claude-opus-5-5", "Quando gioca il Bari?", tools, user_id=None) == "Il Bari gioca venerdì."
    assert seen == ["Bari"]
    second = client.calls[1]["messages"]
    assert second[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "id 7 Bari - Catania"}
    assert client.calls[0]["tools"][0]["strict"] is True
    assert db.query(UsageEvent).filter(UsageEvent.source == "ai:ask:opus-5-5").count() == 2


def test_tool_errors_go_back_to_the_model_and_steps_are_limited(db):
    def broken(match_id):
        raise ValueError("partita non trovata")

    tools = [Tool("scheda_partita", "Scheda", {"match_id": "Id"}, broken, ("match_id",))]
    client = FakeClient([tool_call("scheda_partita", {"match_id": 1}), text("Non trovo la partita.")])
    ai = Ai(db, "k", Settings(ai_monthly_budget_eur=10), client=client)
    assert ask(ai, "claude-opus-5-5", "Scheda?", tools) == "Non trovo la partita."
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True
    endless = FakeClient([tool_call("scheda_partita", {"match_id": 1}, f"t{i}") for i in range(10)])
    with pytest.raises(AiError):
        ask(Ai(db, "k", Settings(ai_monthly_budget_eur=10), client=endless), "claude-opus-5-5", "x", tools)


def test_ask_endpoint_saves_history_and_uses_real_tools(logged_client, db, monkeypatch):
    from app.ai import ask as ask_module
    from app.api import ask as ask_api

    comp = Competition(code="ITA-B", name="Serie B", country="Italia", tier=2)
    bari, cat = Team(name="Bari", country="Italia"), Team(name="Catania", country="Italia")
    db.add_all([comp, bari, cat])
    db.flush()
    db.add(Match(competition_id=comp.id, season="2026/27", kickoff_at=datetime.now(UTC) + timedelta(days=2), kickoff_has_time=True,
                 home_team_id=bari.id, away_team_id=cat.id))  # fmt: skip
    db.commit()
    tools_seen = {}

    def fake_ask(ai, model, question, tools, context="", user_id=None, history=None):
        tools_seen.update({t.name: t for t in tools})
        return f"Risposta a: {question} ({len(history or [])} precedenti)"

    monkeypatch.setattr(ask_module, "ask", fake_ask)
    monkeypatch.setattr(ask_api, "get_settings", lambda: Settings(anthropic_api_key="k"))
    first = logged_client.post("/api/ask", json={"question": "Come arriva il Bari?"}).json()
    assert first["answer"] == "Risposta a: Come arriva il Bari? (0 precedenti)"
    second = logged_client.post("/api/ask", json={"question": "E il Catania?"}).json()
    assert second["answer"].endswith("(1 precedenti)")
    assert [q["question"] for q in logged_client.get("/api/ask").json()] == ["E il Catania?", "Come arriva il Bari?"]
    # Gli strumenti veri leggono il database
    assert "Bari - Catania" in tools_seen["cerca_partite"].run(squadra="bar")
    assert "nessuna notizia" in tools_seen["notizie_squadra"].run(squadra="Bari")
    assert "non ha ancora registrato" in tools_seen["le_mie_giocate"].run()
    assert "Nessuna quota con valore" in tools_seen["occasioni"].run()
