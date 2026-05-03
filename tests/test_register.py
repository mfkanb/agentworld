"""US-001 Agent 注册接口测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_register_success(client: AsyncClient):
    resp = await client.post("/api/agents/register", json={
        "username": "testbot",
        "nickname": "Test Bot",
        "bio": "I am a test agent",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "verification_code" in data["data"]
    assert "challenge_text" in data["data"]
    assert data["message"]


@pytest.mark.anyio
async def test_register_duplicate_username(client: AsyncClient):
    payload = {"username": "dupbot", "nickname": "Dup"}
    resp1 = await client.post("/api/agents/register", json=payload)
    assert resp1.json()["success"] is True

    resp2 = await client.post("/api/agents/register", json=payload)
    assert resp2.json()["success"] is False
    assert resp2.json()["error"] == "username_taken"


@pytest.mark.anyio
async def test_register_invalid_username(client: AsyncClient):
    cases = ["AB", "a" * 51, "has space", "中文", "UPPERCASE", "a!b@c"]
    for username in cases:
        resp = await client.post("/api/agents/register", json={"username": username})
        assert resp.status_code == 422, f"'{username}' should be rejected"


@pytest.mark.anyio
async def test_register_username_min_length(client: AsyncClient):
    resp = await client.post("/api/agents/register", json={"username": "a"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_optional_fields(client: AsyncClient):
    resp = await client.post("/api/agents/register", json={
        "username": "minimalbot",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_register_challenge_text_obfuscated(client: AsyncClient):
    resp = await client.post("/api/agents/register", json={
        "username": "obfbot",
    })
    data = resp.json()["data"]
    challenge = data["challenge_text"]
    assert len(challenge) > 0
