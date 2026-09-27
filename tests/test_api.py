from tests.conftest import auth


def seed(load):
    load("NIFTY 50", [100, 101, 99, 102], kind="INDEX")
    load("RELIANCE", [1000, 1010, 990, 1020])


def test_requires_login(client):
    assert client.get("/api/account").status_code == 401
    assert client.get("/api/account", headers={"Authorization": "Bearer dev:x"}).status_code == 401


def test_manual_trade_flow(client, load):
    seed(load)
    quotes = client.get("/api/market/quotes").json()
    assert quotes[0]["symbol"] == "NIFTY 50"
    response = client.post("/api/orders", json={"symbol": "RELIANCE", "side": "BUY", "quantity": 10}, headers=auth("asha"))
    assert response.status_code == 201, response.text
    assert response.json()["price"] == 1020
    account = client.get("/api/account", headers=auth("asha")).json()
    assert account["cash"] == 1_000_000 - 10_200
    assert account["positions"][0]["quantity"] == 10
    bad = client.post("/api/orders", json={"symbol": "RELIANCE", "side": "SELL", "quantity": 11}, headers=auth("asha"))
    assert bad.status_code == 422
    assert len(client.get("/api/orders", headers=auth("asha")).json()) == 1
    board = client.get("/api/leaderboard").json()
    assert [(e["handle"], e["return_pct"]) for e in board["entries"]] == [("asha", 0.0)]


def test_strategy_crud_and_backtest(client, load):
    seed(load)
    params = {"watch_symbol": "NIFTY 50", "direction": "down", "threshold_pct": 1.5, "trade_symbol": "RELIANCE", "quantity": 5}
    preview = client.post("/api/strategies/backtest", json={"rule_type": "prev_close_move", "params": params, "days": 10},
                          headers=auth("asha"))
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["trades"]) == 1
    created = client.post("/api/strategies", json={"name": "Dip buyer", "rule_type": "prev_close_move", "params": params},
                          headers=auth("asha")).json()
    assert created["description"].startswith("If NIFTY 50 drops 1.5%")
    other = client.patch(f"/api/strategies/{created['id']}", json={"active": False}, headers=auth("ravi"))
    assert other.status_code == 404
    assert client.patch(f"/api/strategies/{created['id']}", json={"active": False}, headers=auth("asha")).json()["active"] is False
    unknown = client.post("/api/strategies", json={"name": "x", "rule_type": "sma_cross",
                                                   "params": {"symbol": "NOPE", "period": 5, "quantity": 1}}, headers=auth("asha"))
    assert unknown.status_code == 422
    assert client.delete(f"/api/strategies/{created['id']}", headers=auth("asha")).status_code == 204


def test_admin_requires_token(client):
    assert client.post("/api/admin/run-daily").status_code == 403


def test_leaderboard_is_public(client):
    assert client.get("/api/leaderboard").status_code == 200


def test_terminal_endpoints(client, load):
    seed(load)
    assert client.post("/api/command", json={"text": "reliance"}).json()["symbol"] == "RELIANCE"
    assert client.get("/api/market/movers").status_code == 200
    assert client.get("/api/market/heatmap").status_code == 200
    assert client.get("/api/market/describe", params={"symbol": "RELIANCE"}).json()["close"] == 1020
    assert client.get("/api/market/chart", params={"symbol": "RELIANCE", "indicators": "sma20"}).status_code == 200
    client.post("/api/orders", json={"symbol": "RELIANCE", "side": "BUY", "quantity": 10}, headers=auth("asha"))
    assert client.post("/api/orders", json={"symbol": "RELIANCE", "side": "BUY"}, headers=auth("asha")).status_code == 422
    sold = client.post("/api/orders", json={"symbol": "RELIANCE", "side": "SELL"}, headers=auth("asha"))
    assert sold.status_code == 201 and sold.json()["quantity"] == 10
    stats = client.get("/api/account/analytics", headers=auth("asha")).json()
    assert stats["closed_trades"] == 1 and stats["realized_pnl"] == 0
