import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimiter


def _make_test_app():
    app = FastAPI()
    limiter = RateLimiter(max_requests=3, window_seconds=3600)

    @app.post("/limited")
    def limited_endpoint(_=Depends(limiter)):
        return {"ok": True}

    return app, limiter


def test_allows_requests_under_the_limit():
    app, _ = _make_test_app()
    client = TestClient(app)
    for _ in range(3):
        response = client.post("/limited")
        assert response.status_code == 200


def test_blocks_requests_over_the_limit():
    app, _ = _make_test_app()
    client = TestClient(app)
    for _ in range(3):
        client.post("/limited")
    response = client.post("/limited")
    assert response.status_code == 429


def test_limits_are_tracked_per_ip_independently():
    app, limiter = _make_test_app()
    client = TestClient(app)
    for _ in range(3):
        client.post("/limited", headers={"X-Forwarded-For": "1.1.1.1"})
    # andere IP darf noch
    response = client.post("/limited", headers={"X-Forwarded-For": "2.2.2.2"})
    assert response.status_code == 200
    # erste IP bleibt blockiert
    response = client.post("/limited", headers={"X-Forwarded-For": "1.1.1.1"})
    assert response.status_code == 429
