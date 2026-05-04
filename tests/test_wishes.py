"""US-014 许愿墙 API 测试"""
import uuid

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
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM wish_votes")
    await db.execute("DELETE FROM wishes")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "wishuser") -> tuple[str, str]:
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


# --- POST /api/wishes ---


@pytest.mark.anyio
async def test_create_wish(client: AsyncClient):
    """AC-1: 发布心愿"""
    _, api_key = await _create_active_agent(client, "user1")

    resp = await client.post(
        "/api/wishes",
        json={"content": "希望有更好的AI工具"},
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["content"] == "希望有更好的AI工具"
    assert data["data"]["status"] == "pending"
    assert data["data"]["vote_count"] == 0


@pytest.mark.anyio
async def test_create_wish_adds_xiami(client: AsyncClient):
    """AC-1: 发布心愿 +2 虾米"""
    agent_id, api_key = await _create_active_agent(client, "user2")

    db = await get_db()
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT OR REPLACE INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 10, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    await client.post(
        "/api/wishes",
        json={"content": "希望有更多虾米"},
        headers=_auth_header(api_key),
    )

    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = ?",
        (agent_id,),
    )
    row = await cursor.fetchone()
    assert row["balance"] == 12  # 10 + 2


@pytest.mark.anyio
async def test_create_wish_max_3(client: AsyncClient):
    """AC-1: 最多 3 个待实现心愿"""
    _, api_key = await _create_active_agent(client, "user3")

    for i in range(3):
        resp = await client.post(
            "/api/wishes",
            json={"content": f"心愿 {i}"},
            headers=_auth_header(api_key),
        )
        assert resp.json()["success"] is True

    # 4th should fail
    resp = await client.post(
        "/api/wishes",
        json={"content": "第4个心愿"},
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert "limit_exceeded" in data["error"]


@pytest.mark.anyio
async def test_create_wish_requires_auth(client: AsyncClient):
    """POST /api/wishes 需要 API Key"""
    resp = await client.post(
        "/api/wishes",
        json={"content": "心愿"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_wish_content_required(client: AsyncClient):
    """content 必填"""
    _, api_key = await _create_active_agent(client, "user4")

    resp = await client.post(
        "/api/wishes",
        json={},
        headers=_auth_header(api_key),
    )
    assert resp.status_code == 422


# --- GET /api/wishes ---


@pytest.mark.anyio
async def test_list_wishes(client: AsyncClient):
    """AC-2: 浏览心愿列表"""
    _, api_key = await _create_active_agent(client, "user5")

    for i in range(3):
        await client.post(
            "/api/wishes",
            json={"content": f"心愿 {i}"},
            headers=_auth_header(api_key),
        )

    resp = await client.get("/api/wishes")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 3
    assert len(data["data"]["items"]) == 3


@pytest.mark.anyio
async def test_list_wishes_no_auth(client: AsyncClient):
    """GET /api/wishes 无需认证"""
    resp = await client.get("/api/wishes")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_list_wishes_pagination(client: AsyncClient):
    """心愿列表分页"""
    _, api_key1 = await _create_active_agent(client, "user6a")
    _, api_key2 = await _create_active_agent(client, "user6b")

    # Create 3 wishes from agent1, 2 from agent2 = 5 total
    for i in range(3):
        await client.post(
            "/api/wishes",
            json={"content": f"心愿 a{i}"},
            headers=_auth_header(api_key1),
        )
    for i in range(2):
        await client.post(
            "/api/wishes",
            json={"content": f"心愿 b{i}"},
            headers=_auth_header(api_key2),
        )

    resp = await client.get("/api/wishes?page=1&limit=2")
    data = resp.json()
    assert data["data"]["total"] == 5
    assert len(data["data"]["items"]) == 2
    assert data["data"]["page"] == 1
    assert data["data"]["limit"] == 2


# --- POST /api/wishes/{id}/vote ---


@pytest.mark.anyio
async def test_vote_wish(client: AsyncClient):
    """AC-3: 投票支持心愿"""
    _, author_key = await _create_active_agent(client, "author1")
    _, voter_key = await _create_active_agent(client, "voter1")

    resp = await client.post(
        "/api/wishes",
        json={"content": "测试心愿"},
        headers=_auth_header(author_key),
    )
    wish_id = resp.json()["data"]["id"]

    resp = await client.post(
        f"/api/wishes/{wish_id}/vote",
        headers=_auth_header(voter_key),
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Check vote count updated
    db = await get_db()
    cursor = await db.execute(
        "SELECT vote_count FROM wishes WHERE wish_id = ?",
        (wish_id,),
    )
    row = await cursor.fetchone()
    assert row["vote_count"] == 1


@pytest.mark.anyio
async def test_vote_gives_xiami_to_author(client: AsyncClient):
    """AC-3: 投票 +1 虾米给发布者"""
    author_id, author_key = await _create_active_agent(client, "author2")
    _, voter_key = await _create_active_agent(client, "voter2")

    resp = await client.post(
        "/api/wishes",
        json={"content": "测试心愿"},
        headers=_auth_header(author_key),
    )
    wish_id = resp.json()["data"]["id"]

    await client.post(
        f"/api/wishes/{wish_id}/vote",
        headers=_auth_header(voter_key),
    )

    # Author should have +1 xiami from vote (plus +2 from creating wish)
    db = await get_db()
    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = ?",
        (author_id,),
    )
    row = await cursor.fetchone()
    assert row["balance"] == 53  # 50 (initial) + 2 (create) + 1 (vote)


@pytest.mark.anyio
async def test_vote_once_per_wish(client: AsyncClient):
    """AC-3: 每人每心愿 1 票"""
    _, author_key = await _create_active_agent(client, "author3")
    _, voter_key = await _create_active_agent(client, "voter3")

    resp = await client.post(
        "/api/wishes",
        json={"content": "测试心愿"},
        headers=_auth_header(author_key),
    )
    wish_id = resp.json()["data"]["id"]

    # First vote succeeds
    resp = await client.post(
        f"/api/wishes/{wish_id}/vote",
        headers=_auth_header(voter_key),
    )
    assert resp.json()["success"] is True

    # Second vote fails
    resp = await client.post(
        f"/api/wishes/{wish_id}/vote",
        headers=_auth_header(voter_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert "already_voted" in data["error"]


@pytest.mark.anyio
async def test_vote_nonexistent_wish(client: AsyncClient):
    """投票给不存在的心愿"""
    _, api_key = await _create_active_agent(client, "user7")

    resp = await client.post(
        "/api/wishes/nonexistent/vote",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert "not_found" in data["error"]


@pytest.mark.anyio
async def test_vote_requires_auth(client: AsyncClient):
    """投票需要认证"""
    resp = await client.post("/api/wishes/some-id/vote")
    assert resp.status_code == 401
