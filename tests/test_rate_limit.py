"""US-023 全局限流中间件测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db
from src.services.rate_limit import limiter


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表并重置限流状态"""
    limiter.reset()

    db = await get_db()
    await db.execute("DELETE FROM reviews")
    await db.execute("DELETE FROM favorites")
    await db.execute("DELETE FROM downloads")
    await db.execute("DELETE FROM skills")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "rluser") -> tuple[str, str]:
    """注册并激活一个 agent，返回 (agent_id, api_key)"""
    resp = await client.post("/api/agents/register", json={"username": username})
    data = resp.json()["data"]
    code = data["verification_code"]

    db = await get_db()
    cursor = await db.execute(
        "SELECT agent_id, challenge_answer FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()

    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": row["challenge_answer"],
    })
    return row["agent_id"], resp.json()["data"]["api_key"]


def _auth_header(api_key: str) -> dict:
    return {"agent-auth-api-key": api_key}


# --- GET rate limit (60/min) ---

@pytest.mark.anyio
async def test_get_within_limit(client: AsyncClient):
    """GET 请求在限额内正常通过"""
    for _ in range(5):
        resp = await client.get("/api/skills")
        assert resp.status_code == 200


@pytest.mark.anyio
async def test_get_rate_limited_returns_429(client: AsyncClient):
    """GET 超过 60 次/分钟返回 429"""
    for _ in range(60):
        await client.get("/api/skills")

    resp = await client.get("/api/skills")
    assert resp.status_code == 429
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "rate_limited"


@pytest.mark.anyio
async def test_get_rate_limited_has_retry_after(client: AsyncClient):
    """限流响应包含 Retry-After Header"""
    for _ in range(60):
        await client.get("/api/skills")

    resp = await client.get("/api/skills")
    assert "retry-after" in resp.headers
    assert int(resp.headers["retry-after"]) > 0


# --- POST rate limit (30/min) ---

@pytest.mark.anyio
async def test_post_rate_limited_returns_429(client: AsyncClient):
    """POST 超过 30 次/分钟返回 429"""
    _, api_key = await _create_active_agent(client, "postlimiter")

    for _ in range(30):
        await client.post(
            "/api/skills",
            json={"name": f"skill-{_}", "description": "test"},
            headers=_auth_header(api_key),
        )

    resp = await client.post(
        "/api/skills",
        json={"name": "overflow-skill", "description": "test"},
        headers=_auth_header(api_key),
    )
    assert resp.status_code == 429


# --- API Key based rate limiting ---

@pytest.mark.anyio
async def test_different_api_keys_separate_limits(client: AsyncClient):
    """不同 API Key 有独立限额"""
    _, key1 = await _create_active_agent(client, "sepuser1")
    _, key2 = await _create_active_agent(client, "sepuser2")

    # key1 uses some quota
    for _ in range(30):
        await client.get("/api/skills", headers=_auth_header(key1))

    # key2 should still work fine
    resp = await client.get("/api/skills", headers=_auth_header(key2))
    assert resp.status_code == 200


# --- Unauthenticated IP-based rate limiting ---

@pytest.mark.anyio
async def test_unauthenticated_uses_ip(client: AsyncClient):
    """未认证请求使用 IP 限流"""
    # Unauthenticated GETs share IP-based limit
    for _ in range(60):
        await client.get("/api/skills")

    resp = await client.get("/api/skills")
    assert resp.status_code == 429


# --- Health endpoint not rate limited ---

@pytest.mark.anyio
async def test_health_not_rate_limited(client: AsyncClient):
    """健康检查端点不受限流影响"""
    for _ in range(65):
        await client.get("/health")

    resp = await client.get("/health")
    assert resp.status_code == 200


# --- Root and docs not rate limited ---

@pytest.mark.anyio
async def test_root_not_rate_limited(client: AsyncClient):
    """根路径 / 不受限流"""
    for _ in range(65):
        await client.get("/")

    resp = await client.get("/")
    assert resp.status_code == 200


# --- Bar routes (non /api/) rate limited ---

@pytest.mark.anyio
async def test_bar_get_drinks_rate_limited(client: AsyncClient):
    """GET /drinks 受限流"""
    for _ in range(60):
        await client.get("/drinks")

    resp = await client.get("/drinks")
    assert resp.status_code == 429


@pytest.mark.anyio
async def test_guestbook_get_rate_limited(client: AsyncClient):
    """GET /guestbook 受限流"""
    for _ in range(60):
        await client.get("/guestbook")

    resp = await client.get("/guestbook")
    assert resp.status_code == 429


@pytest.mark.anyio
async def test_selfies_get_rate_limited(client: AsyncClient):
    """GET /selfies 受限流"""
    for _ in range(60):
        await client.get("/selfies")

    resp = await client.get("/selfies")
    assert resp.status_code == 429
