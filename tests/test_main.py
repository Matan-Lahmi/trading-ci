import os
import pytest

# Set before any src import so database.py picks up the test path at module load time
os.environ["DB_PATH"] = "/tmp/test_trading_tracker.db"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.database import Base, get_db  # noqa: E402
from src.main import app  # noqa: E402

# ── Test database setup ────────────────────────────────────────────────────────

_TEST_DB_URL = "sqlite:////tmp/test_trading_tracker.db"
_test_engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

Base.metadata.create_all(bind=_test_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    path = "/tmp/test_trading_tracker.db"
    if os.path.exists(path):
        os.remove(path)


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_create_trade(client):
    resp = client.post(
        "/api/trades",
        json={
            "symbol": "AAPL",
            "buy_date": "2024-01-15",
            "quantity": 10,
            "entry_price": 185.50,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["buy_date"] == "2024-01-15"
    assert data["quantity"] == 10
    assert data["entry_price"] == 185.50
    assert data["status"] == "open"
    assert data["close_price"] is None
    assert data["close_date"] is None
    assert "id" in data
    assert "created_at" in data


def test_get_trades_structure(client):
    resp = client.get("/api/trades")
    assert resp.status_code == 200
    data = resp.json()
    assert "open" in data
    assert "closed" in data
    assert isinstance(data["open"], list)
    assert isinstance(data["closed"], list)
    # AAPL trade created in test_create_trade must appear in open
    open_symbols = [t["symbol"] for t in data["open"]]
    assert "AAPL" in open_symbols


def test_close_trade(client):
    # Create a dedicated trade so this test is self-contained
    create_resp = client.post(
        "/api/trades",
        json={
            "symbol": "TSLA",
            "buy_date": "2024-03-01",
            "quantity": 5,
            "entry_price": 200.00,
        },
    )
    assert create_resp.status_code == 200
    trade_id = create_resp.json()["id"]

    close_resp = client.put(
        f"/api/trades/{trade_id}/close",
        json={"close_price": 260.00, "close_date": "2024-09-01"},
    )
    assert close_resp.status_code == 200
    data = close_resp.json()
    assert data["id"] == trade_id
    assert data["status"] == "closed"
    assert data["close_price"] == 260.00
    assert data["close_date"] == "2024-09-01"

    # Confirm it moved from open → closed
    all_resp = client.get("/api/trades")
    all_data = all_resp.json()
    open_ids = [t["id"] for t in all_data["open"]]
    closed_ids = [t["id"] for t in all_data["closed"]]
    assert trade_id not in open_ids
    assert trade_id in closed_ids


def test_close_trade_not_found(client):
    resp = client.put(
        "/api/trades/999999/close",
        json={"close_price": 100.00, "close_date": "2024-01-01"},
    )
    assert resp.status_code == 404


def test_delete_trade(client):
    create_resp = client.post(
        "/api/trades",
        json={
            "symbol": "GOOGL",
            "buy_date": "2024-02-01",
            "quantity": 3,
            "entry_price": 140.00,
        },
    )
    assert create_resp.status_code == 200
    trade_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/trades/{trade_id}")
    assert del_resp.status_code == 200

    # Confirm it no longer appears in either list
    all_resp = client.get("/api/trades")
    all_data = all_resp.json()
    all_ids = [t["id"] for t in all_data["open"] + all_data["closed"]]
    assert trade_id not in all_ids


def test_delete_trade_not_found(client):
    resp = client.delete("/api/trades/999999")
    assert resp.status_code == 404
