from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimiter


def _make_request(ip: str) -> Mock:
    request = Mock()
    request.client.host = ip
    request.headers = {}
    return request


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
    # Direkter Unit-Test auf RateLimiter.__call__ mit Mock-Requests, da
    # TestClient keine unterschiedlichen Socket-Client-IPs pro Request
    # simulieren kann (X-Forwarded-For wird bewusst nicht mehr vertraut).
    limiter = RateLimiter(max_requests=3, window_seconds=3600)

    for _ in range(3):
        limiter(_make_request("1.1.1.1"))

    # erste IP ist jetzt blockiert
    with pytest.raises(HTTPException) as exc_info:
        limiter(_make_request("1.1.1.1"))
    assert exc_info.value.status_code == 429

    # andere IP darf noch
    limiter(_make_request("2.2.2.2"))  # löst keine Exception aus
