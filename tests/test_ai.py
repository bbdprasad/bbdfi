import json
from types import SimpleNamespace

import pytest

from bbdfi import ai
from bbdfi.config import get_settings
from bbdfi.engine.rules import parse_rule
from tests.conftest import auth


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued JSON answers and records each request."""

    def __init__(self, *answers, stop_reason="end_turn"):
        self.answers, self.calls, self.stop_reason = list(answers), [], stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = json.dumps(self.answers.pop(0)) if self.answers else ""
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture()
def enable_ai(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("AI_DAILY_LIMIT", "2")
    get_settings.cache_clear()

    def _install(client):
        monkeypatch.setattr(ai, "get_client", lambda: client)
        return client
    yield _install
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.delenv("AI_DAILY_LIMIT")
    get_settings.cache_clear()


def draft(**fields):
    blank = {key: None for key in ai.DRAFT_SCHEMA["required"]}
    return blank | {"supported": True, "reply": "ok", "name": "Dip buyer"} | fields


def seed(load):
    load("NIFTY 50", [100, 101, 99, 102, 100, 98, 101, 103], kind="INDEX")
    load("RELIANCE", [1000, 1010, 990, 1020, 1000, 985, 1010, 1030])


def test_ai_disabled_by_default(client, load):
    seed(load)
    assert client.get("/api/config").json()["ai_enabled"] is False
    response = client.post("/api/ai/strategy", json={"text": "buy reliance on dips"}, headers=auth("asha"))
    assert response.status_code == 503


def test_draft_rule_from_hindi(client, load, enable_ai):
    seed(load)
    fake = enable_ai(FakeClient(draft(rule_type="prev_close_move", watch_symbol="NIFTY 50", direction="down",
                                      threshold_pct=1.5, trade_symbol="RELIANCE", side="BUY", quantity=5,
                                      reply="जब निफ्टी 1.5% गिरे, 5 रिलायंस खरीदें।")))
    response = client.post("/api/ai/strategy", json={"text": "जब निफ्टी 1.5% गिरे तो रिलायंस खरीदो"}, headers=auth("asha"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["supported"] is True
    assert body["params"] == {"watch_symbol": "NIFTY 50", "direction": "down", "threshold_pct": 1.5,
                              "trade_symbol": "RELIANCE", "side": "BUY", "quantity": 5}
    assert body["description"].startswith("If NIFTY 50 drops 1.5%")
    assert body["remaining_today"] == 1
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "RELIANCE" in call["system"] and "Never recommend" in call["system"]


def test_draft_rule_rejects_unknown_symbol_and_unsupported(client, load, enable_ai):
    seed(load)
    enable_ai(FakeClient(draft(rule_type="sma_cross", symbol="TSLA", period=20, quantity=1),
                         draft(supported=False, rule_type="none", reply="Options are not supported yet.")))
    unknown = client.post("/api/ai/strategy", json={"text": "tesla sma"}, headers=auth("asha")).json()
    assert unknown["supported"] is False and "TSLA" in unknown["problem"]
    unsupported = client.post("/api/ai/strategy", json={"text": "sell nifty calls"}, headers=auth("asha")).json()
    assert unsupported == {"reply": "Options are not supported yet.", "name": "Dip buyer", "supported": False,
                           "remaining_today": 0}


def test_daily_limit(client, load, enable_ai):
    seed(load)
    enable_ai(FakeClient(*[draft(supported=False, rule_type="none")] * 3))
    for _ in range(2):
        assert client.post("/api/ai/strategy", json={"text": "anything"}, headers=auth("asha")).status_code == 200
    limited = client.post("/api/ai/strategy", json={"text": "anything"}, headers=auth("asha"))
    assert limited.status_code == 429
    # The limit is per person.
    assert client.post("/api/ai/strategy", json={"text": "anything"}, headers=auth("ravi")).status_code == 200


def test_refusal_is_reported(client, load, enable_ai):
    seed(load)
    enable_ai(FakeClient(stop_reason="refusal"))
    response = client.post("/api/ai/strategy", json={"text": "something odd"}, headers=auth("asha"))
    assert response.status_code == 502
    assert "declined" in response.json()["detail"]


def test_explain_backtest_sends_computed_numbers(client, load, enable_ai):
    seed(load)
    fake = enable_ai(FakeClient({"headline": "Small sample.", "points": ["One trade only."], "caution": "Too few trades."}))
    params = {"watch_symbol": "NIFTY 50", "direction": "down", "threshold_pct": 1.5, "trade_symbol": "RELIANCE", "quantity": 5}
    response = client.post("/api/ai/explain", json={"rule_type": "prev_close_move", "params": params, "days": 7},
                           headers=auth("asha"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["headline"] == "Small sample."
    assert [row["variant"] for row in body["variations"]] == ["your rule", "threshold 0.75%", "threshold 2.25%"]
    assert body["buy_and_hold_symbol"] == "RELIANCE" and body["buy_and_hold_pct"] is not None
    facts = json.loads(fake.calls[0]["messages"][0]["content"])
    assert facts["results"] == body["variations"]


def test_variations_cover_each_rule_type():
    sma = parse_rule("sma_cross", {"symbol": "X", "period": 20, "quantity": 1})
    assert [label for label, _ in ai.variations(sma)] == ["10-day average", "50-day average", "100-day average"]
    exits = parse_rule("take_profit_stop_loss", {"symbol": "X", "take_profit_pct": 10})
    assert [rule.take_profit_pct for _, rule in ai.variations(exits)] == [5, 15]


def test_rule_command_carries_the_idea():
    from bbdfi.commands import parse

    assert parse("rule buy Reliance when Nifty falls 2%", {"RELIANCE"}) == {
        "action": "new_rule", "text": "buy Reliance when Nifty falls 2%"}
    assert parse("RULE", {"RELIANCE"}) == {"action": "new_rule"}
