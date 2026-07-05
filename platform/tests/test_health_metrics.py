def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"edge_http_requests_total" in r.content


def test_ready_reports_checks(client):
    r = client.get("/ready")
    body = r.json()
    assert "checks" in body
    assert body["checks"]["database"] == "ok"  # sqlite is reachable in tests
