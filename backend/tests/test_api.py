"""
backend/tests/test_api.py

Integration and endpoint tests for FastAPI routes using TestClient.
Tests /api/health, /api/actuals, /api/forecasts/latest, and /api/metrics.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.data_service import data_service


@pytest.fixture(scope="module")
def client():
    # Ensure cache is loaded before running tests
    data_service.load_data()
    with TestClient(app) as test_client:
        yield test_client


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert data["docs_url"] == "/docs"


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    cache = data["cache"]
    assert cache["actuals_count"] > 0
    assert cache["forecasts_count"] > 0


def test_actuals_endpoint(client):
    response = client.get("/api/actuals?start_date=2026-01-01&end_date=2026-01-02")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    # 2 days * 48 settlement periods = 96 records
    assert len(payload["data"]) == 96
    sample = payload["data"][0]
    assert sample["fuelType"] == "WIND"
    assert sample["settlementPeriod"] == 1
    assert "generation" in sample


def test_forecasts_latest_endpoint(client):
    response = client.get("/api/forecasts/latest?start_date=2026-01-01&end_date=2026-01-01&cutoff_time=09:00")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    # 24 hourly forecasts for 1 day
    assert len(payload["data"]) == 24
    sample = payload["data"][0]
    assert "generation" in sample
    assert "publishTime" in sample
    assert "horizonHours" in sample
    # Verification: publishTime must be <= 2025-12-31 09:00:00Z
    assert sample["publishTime"] <= "2025-12-31T09:00:00Z"


def test_metrics_endpoint(client):
    response = client.get("/api/metrics?start_date=2026-01-01&end_date=2026-01-07&cutoff_time=09:00")
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    summary = payload["summary"]
    # 7 days * 48 settlement periods = 336
    assert summary["sampleCount"] == 336
    assert summary["mae"] > 0
    assert summary["rmse"] > 0
    assert "nmaeCapacity" in summary
    assert "horizonMetrics" in payload
    assert len(payload["horizonMetrics"]) > 0
    assert "series" in payload
    assert len(payload["series"]) == 336


def test_invalid_date_returns_422(client):
    """FastAPI date validation returns 422 Unprocessable Entity for malformed date strings."""
    response = client.get("/api/metrics?start_date=not-a-date")
    assert response.status_code == 422
    assert "start_date" in response.text


def test_invalid_cutoff_time_pattern_returns_422(client):
    """FastAPI regex validation returns 422 for malformed cutoff_time strings."""
    response = client.get("/api/metrics?cutoff_time=9:0")
    assert response.status_code == 422
    assert "cutoff_time" in response.text


def test_refresh_endpoint_unauthorized_when_secret_set(client, monkeypatch):
    """When REFRESH_SECRET is set, requests without valid token return 403."""
    import backend.app.routes.api as routes_api
    monkeypatch.setattr(routes_api, "REFRESH_SECRET", "super-secret-token")

    response = client.post("/api/refresh")
    assert response.status_code == 403

    # With invalid header
    response = client.post("/api/refresh", headers={"x-refresh-token": "wrong"})
    assert response.status_code == 403
