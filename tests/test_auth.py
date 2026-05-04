"""US-004 API Key 认证中间件测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_active_agent(client: AsyncClient, username: str = "authbot") -> str:
    """注册并激活一个 agent，返回 api_key"""
    resp = await client.post("/api/agents/register", json={"username": username})
    data = resp.json()["data"]
    code = data["verification_code"]

    # 从数据库读答案
    db = await get_db()
    cursor = await db.execute(
        "SELECT challenge_answer FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()
    answer = row["challenge_answer"]

    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": answer,
    })
    return resp.json()["data"]["api_key"]


@pytest.mark.anyio
async def test_auth_with_api_key_header(client: AsyncClient):
    """从 agent-auth-api-key Header 提取 API Key"""
    api_key = await _create_active_agent(client, "headerbot")
    resp = await client.get("/api/agents/me", headers={
        "agent-auth-api-key": api_key,
    })
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["username"] == "headerbot"
    assert "agent_id" in data["data"]


@pytest.mark.anyio
async def test_auth_with_bearer_header(client: AsyncClient):
    """支持 Authorization: Bearer 方式"""
    api_key = await _create_active_agent(client, "bearerbot")
    resp = await client.get("/api/agents/me", headers={
        "Authorization": f"Bearer {api_key}",
    })
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["username"] == "bearerbot"


@pytest.mark.anyio
async def test_auth_missing_key(client: AsyncClient):
    """缺少 API Key 返回 401 含 hint"""
    resp = await client.get("/api/agents/me")
    assert resp.status_code == 401
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "auth_failed"
    assert data["hint"]
    assert data["request_id"].startswith("req_")


@pytest.mark.anyio
async def test_auth_invalid_key(client: AsyncClient):
    """无效 Key 返回 401 含 hint"""
    resp = await client.get("/api/agents/me", headers={
        "agent-auth-api-key": "agent-world-" + "0" * 48,
    })
    assert resp.status_code == 401
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "auth_failed"
    assert data["hint"]
    assert data["request_id"].startswith("req_")


@pytest.mark.anyio
async def test_auth_inactive_account(client: AsyncClient):
    """未激活账号返回 403"""
    # 注册但不激活
    resp = await client.post("/api/agents/register", json={"username": "inactivebot"})
    data = resp.json()["data"]

    # 手动设置一个 api_key 给未激活账号
    db = await get_db()
    await db.execute(
        "UPDATE agents SET api_key = ? WHERE username = ?",
        ("agent-world-" + "a" * 48, "inactivebot"),
    )
    await db.commit()

    resp = await client.get("/api/agents/me", headers={
        "agent-auth-api-key": "agent-world-" + "a" * 48,
    })
    assert resp.status_code == 403
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "unauthorized"
    assert data["hint"]
    assert data["request_id"].startswith("req_")


@pytest.mark.anyio
async def test_auth_returns_agent_info(client: AsyncClient):
    """中间件返回 agent_id 和 username"""
    api_key = await _create_active_agent(client, "infobot")
    resp = await client.get("/api/agents/me", headers={
        "agent-auth-api-key": api_key,
    })
    data = resp.json()["data"]
    assert "agent_id" in data
    assert "username" in data
    assert data["username"] == "infobot"


@pytest.mark.anyio
async def test_auth_bearer_priority(client: AsyncClient):
    """当两种 header 都存在时，agent-auth-api-key 优先"""
    api_key = await _create_active_agent(client, "prioritybot")
    resp = await client.get("/api/agents/me", headers={
        "agent-auth-api-key": api_key,
        "Authorization": "Bearer invalid-key",
    })
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["username"] == "prioritybot"
