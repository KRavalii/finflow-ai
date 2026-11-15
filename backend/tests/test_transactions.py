import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import database
from app.main import app


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(database, "get_engine", lambda: engine)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def payload():
    return {"description": "Groceries", "amount": "42.75", "category": "Food",
            "transaction_type": "expense", "transaction_date": "2026-11-12"}


def test_crud(client, payload):
    assert client.get("/").json()["message"] == "Welcome to FinFlow AI"
    assert client.get("/api/health").json()["status"] == "healthy"
    response = client.post("/api/transactions", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["amount"] == "42.75"
    assert created["created_at"]
    path = f"/api/transactions/{created['id']}"
    assert client.get(path).json() == created
    assert len(client.get("/api/transactions").json()) == 1
    assert client.get("/api/transactions?offset=1&limit=1").json() == []
    response = client.put(path, json={**payload, "amount": "18.50", "description": "Updated"})
    assert response.status_code == 200
    assert response.json()["amount"] == "18.50"
    assert response.json()["created_at"] == created["created_at"]
    assert client.get(path).json()["description"] == "Updated"
    response = client.delete(path)
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("changes", [
    {"amount": "0"}, {"amount": "-1"}, {"amount": "1.234"},
    {"amount": "1000000000000.00"}, {"amount": "NaN"},
    {"description": "   "}, {"description": "x" * 501},
    {"category": ""}, {"transaction_type": "transfer"},
    {"transaction_date": "bad-date"}, {"id": 9},
])
def test_validation(client, payload, changes):
    assert client.post("/api/transactions", json={**payload, **changes}).status_code == 422
    assert client.get("/api/transactions").json() == []


def test_missing_and_invalid_requests(client, payload):
    assert client.get("/api/transactions/999").status_code == 404
    assert client.put("/api/transactions/999", json=payload).status_code == 404
    assert client.delete("/api/transactions/999").status_code == 404
    assert client.put("/api/transactions/999", json={"amount": "1"}).status_code == 422
    for path in ("/api/transactions/0", "/api/transactions?limit=101", "/api/transactions?offset=-1"):
        assert client.get(path).status_code == 422


def test_database_failure_is_sanitized(client):
    def failing_db():
        raise OperationalError("SECRET_SQL", {}, Exception("SECRET_PASSWORD"))
        yield

    app.dependency_overrides[get_db] = failing_db
    response = client.get("/api/transactions")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database operation unavailable"}
    assert "SECRET" not in response.text


def test_failed_write_rolls_back_and_recovers(client, payload, monkeypatch):
    original_commit = Session.commit
    original_rollback = Session.rollback
    calls = {"commits": 0, "rollbacks": 0}

    def commit(session):
        calls["commits"] += 1
        if calls["commits"] == 1:
            session.flush()
            raise OperationalError("PRIVATE_SQL", {}, Exception("PRIVATE_DATABASE_ERROR"))
        return original_commit(session)

    def rollback(session):
        calls["rollbacks"] += 1
        return original_rollback(session)

    monkeypatch.setattr(Session, "commit", commit)
    monkeypatch.setattr(Session, "rollback", rollback)
    response = client.post("/api/transactions", json=payload)
    assert response.status_code == 503
    assert "PRIVATE" not in response.text
    assert calls["rollbacks"] == 1
    assert client.get("/api/transactions").json() == []
    assert client.post("/api/transactions", json=payload).status_code == 201
    assert len(client.get("/api/transactions").json()) == 1
