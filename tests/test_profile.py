"""US-005 Profile 查询与修改测试"""
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


async def _create_active_agent(client: AsyncClient, username: str = "profilebot") -> str:
    """注册并激活一个 agent，返回 api_key"""
    resp = await client.post("/api/agents/register", json={
        "username": username,
        "nickname": "Initial Nick",
        "bio": "Initial bio",
    })
    data = resp.json()["data"]
    code = data["verification_code"]

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
async def test_get_profile_public(client: AsyncClient):
    """GET /api/agents/profile/{username} 无需认证"""
    api_key = await _create_active_agent(client, "publicbot")
    resp = await client.get("/api/agents/profile/publicbot")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["username"] == "publicbot"
    assert "nickname" in data["data"]
    assert "avatar_url" in data["data"]
    assert "bio" in data["data"]
    assert "created_at" in data["data"]


@pytest.mark.anyio
async def test_get_profile_not_found(client: AsyncClient):
    """不存在返回 404"""
    resp = await client.get("/api/agents/profile/nonexistent")
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_get_profile_returns_fields(client: AsyncClient):
    """返回 username/nickname/avatar_url/bio/created_at"""
    await _create_active_agent(client, "fieldsbot")
    resp = await client.get("/api/agents/profile/fieldsbot")
    data = resp.json()["data"]
    assert data["username"] == "fieldsbot"
    assert data["nickname"] == "Initial Nick"
    assert data["bio"] == "Initial bio"
    assert data["avatar_url"] == ""
    assert "created_at" in data


@pytest.mark.anyio
async def test_update_profile_needs_auth(client: AsyncClient):
    """PUT /api/agents/profile 需要 API Key"""
    resp = await client.put("/api/agents/profile", json={"nickname": "new"})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_update_profile_nickname(client: AsyncClient):
    """PUT 更新 nickname"""
    api_key = await _create_active_agent(client, "nickbot")
    resp = await client.put(
        "/api/agents/profile",
        json={"nickname": "Updated Nick"},
        headers={"agent-auth-api-key": api_key},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["nickname"] == "Updated Nick"
    assert data["data"]["username"] == "nickbot"


@pytest.mark.anyio
async def test_update_profile_bio(client: AsyncClient):
    """PUT 更新 bio"""
    api_key = await _create_active_agent(client, "biobot")
    resp = await client.put(
        "/api/agents/profile",
        json={"bio": "Updated bio text"},
        headers={"agent-auth-api-key": api_key},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["bio"] == "Updated bio text"


@pytest.mark.anyio
async def test_update_profile_nickname_too_long(client: AsyncClient):
    """nickname > 100 字符返回 422"""
    api_key = await _create_active_agent(client, "longnickbot")
    resp = await client.put(
        "/api/agents/profile",
        json={"nickname": "x" * 101},
        headers={"agent-auth-api-key": api_key},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_profile_bio_too_long(client: AsyncClient):
    """bio > 500 字符返回 422"""
    api_key = await _create_active_agent(client, "longbiobot")
    resp = await client.put(
        "/api/agents/profile",
        json={"bio": "x" * 501},
        headers={"agent-auth-api-key": api_key},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_profile_cannot_modify_username(client: AsyncClient):
    """不允许修改 username 和 agent_id - 请求体只有 nickname/bio"""
    api_key = await _create_active_agent(client, "lockbot")
    resp = await client.put(
        "/api/agents/profile",
        json={"nickname": "New Lock", "bio": "New bio"},
        headers={"agent-auth-api-key": api_key},
    )
    data = resp.json()
    assert data["success"] is True
    # username 不变
    assert data["data"]["username"] == "lockbot"


@pytest.mark.anyio
async def test_update_profile_bearer_auth(client: AsyncClient):
    """PUT 支持 Authorization: Bearer 方式"""
    api_key = await _create_active_agent(client, "bearerprofilebot")
    resp = await client.put(
        "/api/agents/profile",
        json={"nickname": "Bearer Updated"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["nickname"] == "Bearer Updated"
