import os
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / "_tmp_niteos_hunt_test.db"
os.environ["DEMO_MODE"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_providers():
    r = client.get("/api/providers")
    assert r.status_code == 200
    assert r.json()["object"] == "demo"


def test_demo_hunt_end_to_end():
    r = client.post("/api/hunts", json={"city": "Казань", "query": "завод", "count": 2})
    assert r.status_code == 200
    hid = r.json()["id"]
    h = client.get(f"/api/hunts/{hid}").json()
    assert h["status"] == "completed"
    rows = client.get(f"/api/hunts/{hid}/results").json()
    assert len(rows) == 2
    assert rows[0]["object"]["cadastral_number"]
    assert rows[0]["object"]["photo_url"]
    assert rows[0]["verification"]["status"] == "verified"
    assert rows[0]["verification"]["score"] == 100
    assert rows[0]["company"]["inn"]
    assert rows[0]["people"]
    assert any(p["contacts"] for p in rows[0]["people"])
