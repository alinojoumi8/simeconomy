from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app, orch

ROOT = Path(__file__).resolve().parents[1]


def test_health_and_step():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    orch.reset(seed=99)
    r = client.post("/step", json={"n": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["tick"] == 3
    assert "metrics" in data

    r = client.post("/shock", json={"type": "rate_hike", "params": {"bps": 25}})
    assert r.status_code == 200
    assert r.json().get("ok") is True

    r = client.post("/pause")
    assert r.json()["paused"] is True
