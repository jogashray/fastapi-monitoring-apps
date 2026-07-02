"""End-to-end tests for HTTP endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_root_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "message" in body
    assert "app" in body
    assert "version" in body


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body
    assert "app" in body


@pytest.mark.asyncio
async def test_health_ready_endpoint(client):
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["status"] in ("ready", "not_ready")


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]
    body = response.text
    assert "# HELP" in body
    assert "# TYPE" in body


@pytest.mark.asyncio
async def test_post_data_valid(client):
    payload = {"payload": {"key": "value"}, "note": "hello"}
    response = await client.post("/data", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["received"] == payload
    assert body["size"] > 0
    assert "created_at" in body


@pytest.mark.asyncio
async def test_post_data_invalid(client):
    # Note field has wrong type → 422 from FastAPI validation
    response = await client.post("/data", json={"payload": {"k": "v"}, "note": 12345})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_data_returns_list(client):
    response = await client.get("/data")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_data_round_trip(client):
    # Create then read
    created = await client.post("/data", json={"payload": {"a": 1}})
    assert created.status_code == 201
    cid = created.json()["id"]

    listed = await client.get("/data")
    assert listed.status_code == 200
    items = listed.json()
    assert any(item["id"] == cid for item in items)


@pytest.mark.asyncio
async def test_data_pagination(client):
    for i in range(5):
        await client.post("/data", json={"payload": {"i": i}})

    limited = await client.get("/data", params={"limit": 2})
    assert len(limited.json()) == 2

    offset = await client.get("/data", params={"offset": 3})
    assert len(offset.json()) >= 1


@pytest.mark.asyncio
async def test_data_count(client):
    await client.post("/data", json={"payload": {"x": 1}})
    await client.post("/data", json={"payload": {"x": 2}})
    response = await client.get("/data/count")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 2
