"""US-011 虾评-技能发布更新删除测试"""
import uuid
from datetime import datetime, timezone

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


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空 skills 和 wallets 表"""
    db = await get_db()
    await db.execute("DELETE FROM skills")
    await db.execute("DELETE FROM wallets")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "crudauthor") -> tuple[str, str]:
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


# --- POST /api/skills ---

@pytest.mark.anyio
async def test_create_skill_success(client: AsyncClient):
    """发布技能成功"""
    agent_id, api_key = await _create_active_agent(client, "publisher1")
    resp = await client.post(
        "/api/skills",
        json={"name": "my-skill", "description": "A great skill", "category": "tools"},
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "my-skill"
    assert data["data"]["category"] == "tools"
    assert data["data"]["status"] == "draft"
    assert data["data"]["author"] == "publisher1"


@pytest.mark.anyio
async def test_create_skill_name_required(client: AsyncClient):
    """name 必填"""
    _, api_key = await _create_active_agent(client, "publisher2")
    resp = await client.post(
        "/api/skills",
        json={"description": "no name"},
        headers=_auth_header(api_key),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_skill_requires_auth(client: AsyncClient):
    """需要 API Key"""
    resp = await client.post(
        "/api/skills",
        json={"name": "no-auth-skill"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_skill_awards_10_xiami(client: AsyncClient):
    """发布后 +10 虾米到 wallets"""
    agent_id, api_key = await _create_active_agent(client, "xiami_author")
    resp = await client.post(
        "/api/skills",
        json={"name": "paid-skill"},
        headers=_auth_header(api_key),
    )
    assert resp.json()["success"] is True

    db = await get_db()
    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = ?",
        (agent_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row["balance"] == 60


@pytest.mark.anyio
async def test_create_skill_multiple_accumulates_xiami(client: AsyncClient):
    """多次发布累计虾米"""
    agent_id, api_key = await _create_active_agent(client, "multi_author")
    for i in range(3):
        resp = await client.post(
            "/api/skills",
            json={"name": f"skill-{i}"},
            headers=_auth_header(api_key),
        )
        assert resp.json()["success"] is True

    db = await get_db()
    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = ?",
        (agent_id,),
    )
    row = await cursor.fetchone()
    assert row["balance"] == 80


# --- PUT /api/skills/{id} ---

@pytest.mark.anyio
async def test_update_skill_success(client: AsyncClient):
    """作者更新技能成功"""
    _, api_key = await _create_active_agent(client, "updauthor")
    resp = await client.post(
        "/api/skills",
        json={"name": "original"},
        headers=_auth_header(api_key),
    )
    skill_id = resp.json()["data"]["id"]

    resp = await client.put(
        f"/api/skills/{skill_id}",
        json={"name": "updated", "description": "new desc"},
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "updated"
    assert data["data"]["description"] == "new desc"


@pytest.mark.anyio
async def test_update_skill_non_author_forbidden(client: AsyncClient):
    """非作者返回 forbidden"""
    _, api_key1 = await _create_active_agent(client, "owner")
    _, api_key2 = await _create_active_agent(client, "stranger")

    resp = await client.post(
        "/api/skills",
        json={"name": "owned-skill"},
        headers=_auth_header(api_key1),
    )
    skill_id = resp.json()["data"]["id"]

    resp = await client.put(
        f"/api/skills/{skill_id}",
        json={"name": "hacked"},
        headers=_auth_header(api_key2),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "forbidden"


@pytest.mark.anyio
async def test_update_skill_not_found(client: AsyncClient):
    """更新不存在的技能"""
    _, api_key = await _create_active_agent(client, "updnotfound")
    fake_id = str(uuid.uuid4())
    resp = await client.put(
        f"/api/skills/{fake_id}",
        json={"name": "ghost"},
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


# --- DELETE /api/skills/{id} ---

@pytest.mark.anyio
async def test_delete_skill_success(client: AsyncClient):
    """软删除成功"""
    _, api_key = await _create_active_agent(client, "delauthor")
    resp = await client.post(
        "/api/skills",
        json={"name": "to-delete"},
        headers=_auth_header(api_key),
    )
    skill_id = resp.json()["data"]["id"]

    resp = await client.delete(
        f"/api/skills/{skill_id}",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["deleted_at"] is not None

    # Verify soft deleted - get detail returns not found
    resp = await client.get(f"/api/skills/{skill_id}")
    assert resp.json()["success"] is False
    assert resp.json()["error"] == "not_found"


@pytest.mark.anyio
async def test_delete_skill_non_author_forbidden(client: AsyncClient):
    """非作者不能删除"""
    _, api_key1 = await _create_active_agent(client, "delowner")
    _, api_key2 = await _create_active_agent(client, "delstranger")

    resp = await client.post(
        "/api/skills",
        json={"name": "protected-skill"},
        headers=_auth_header(api_key1),
    )
    skill_id = resp.json()["data"]["id"]

    resp = await client.delete(
        f"/api/skills/{skill_id}",
        headers=_auth_header(api_key2),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "forbidden"


@pytest.mark.anyio
async def test_delete_skill_not_found(client: AsyncClient):
    """删除不存在的技能"""
    _, api_key = await _create_active_agent(client, "delnotfound")
    fake_id = str(uuid.uuid4())
    resp = await client.delete(
        f"/api/skills/{fake_id}",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"
