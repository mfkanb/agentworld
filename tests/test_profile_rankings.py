"""US-015 个人中心与排行榜 API 测试"""
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
    await db.execute("DELETE FROM downloads")
    await db.execute("DELETE FROM favorites")
    await db.execute("DELETE FROM reviews")
    await db.execute("DELETE FROM skills")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "testuser") -> tuple[str, str]:
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


async def _insert_skill(agent_id: str, name: str = "测试技能", category: str = "") -> str:
    """直接插入一条技能记录"""
    db = await get_db()
    skill_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT INTO skills (skill_id, author_id, name, description, category, version, status, downloads, rating, rating_count, created_at) "
        "VALUES (?, ?, ?, '描述', ?, 'draft', 'draft', 0, 0, 0, ?)",
        (skill_id, agent_id, name, category, now),
    )
    await db.commit()
    return skill_id


async def _insert_download(agent_id: str, skill_id: str) -> str:
    """直接插入一条下载记录"""
    db = await get_db()
    download_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT INTO downloads (download_id, agent_id, skill_id, version, created_at) "
        "VALUES (?, ?, ?, 'draft', ?)",
        (download_id, agent_id, skill_id, now),
    )
    await db.commit()
    return download_id


# --- GET /api/auth/me ---


@pytest.mark.anyio
async def test_auth_me_basic(client: AsyncClient):
    """AC-1: GET /api/auth/me 返回虾米余额和等级"""
    agent_id, api_key = await _create_active_agent(client, "user1")

    resp = await client.get("/api/auth/me", headers=_auth_header(api_key))
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["agent_id"] == agent_id
    assert data["data"]["username"] == "user1"
    assert "balance" in data["data"]
    assert "level" in data["data"]


@pytest.mark.anyio
async def test_auth_me_balance(client: AsyncClient):
    """AC-1: 返回正确的虾米余额"""
    agent_id, api_key = await _create_active_agent(client, "user2")

    # Set balance
    db = await get_db()
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 150, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/auth/me", headers=_auth_header(api_key))
    data = resp.json()
    assert data["data"]["balance"] == 150


@pytest.mark.anyio
async def test_auth_me_level(client: AsyncClient):
    """AC-2: 等级按虾米自动计算 A1 到 A4-1"""
    agent_id, api_key = await _create_active_agent(client, "user3")
    db = await get_db()
    now = "2026-01-01T00:00:00"

    levels = [
        (0, "A1"),
        (50, "A1"),
        (100, "A2-1"),
        (200, "A2-1"),
        (500, "A2-2"),
        (800, "A2-2"),
        (1000, "A3-1"),
        (2000, "A3-1"),
        (3000, "A3-2"),
        (8000, "A3-2"),
        (10000, "A4-1"),
        (50000, "A4-1"),
    ]

    for balance, expected_level in levels:
        # Update balance
        await db.execute(
            "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(agent_id) DO UPDATE SET balance = ?",
            (str(uuid.uuid4()), agent_id, balance, now, now, balance),
        )
        await db.commit()

        resp = await client.get("/api/auth/me", headers=_auth_header(api_key))
        data = resp.json()
        assert data["data"]["level"] == expected_level, f"Balance {balance}: expected {expected_level}, got {data['data']['level']}"


@pytest.mark.anyio
async def test_auth_me_requires_auth(client: AsyncClient):
    """GET /api/auth/me 需要 API Key"""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_auth_me_no_wallet(client: AsyncClient):
    """无钱包记录时余额为0"""
    _, api_key = await _create_active_agent(client, "user4")

    resp = await client.get("/api/auth/me", headers=_auth_header(api_key))
    data = resp.json()
    assert data["data"]["balance"] == 0
    assert data["data"]["level"] == "A1"


# --- GET /api/me/skills ---


@pytest.mark.anyio
async def test_my_skills(client: AsyncClient):
    """AC-3: 我的技能列表"""
    agent_id, api_key = await _create_active_agent(client, "user5")

    skill_id = await _insert_skill(agent_id, "我的技能1", "AI")

    resp = await client.get("/api/me/skills", headers=_auth_header(api_key))
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["id"] == skill_id
    assert data["data"]["items"][0]["name"] == "我的技能1"


@pytest.mark.anyio
async def test_my_skills_pagination(client: AsyncClient):
    """技能列表分页"""
    agent_id, api_key = await _create_active_agent(client, "user6")

    for i in range(5):
        await _insert_skill(agent_id, f"技能{i}")

    resp = await client.get("/api/me/skills?page=1&limit=3", headers=_auth_header(api_key))
    data = resp.json()
    assert data["data"]["total"] == 5
    assert len(data["data"]["items"]) == 3
    assert data["data"]["page"] == 1
    assert data["data"]["limit"] == 3


@pytest.mark.anyio
async def test_my_skills_requires_auth(client: AsyncClient):
    """GET /api/me/skills 需要 API Key"""
    resp = await client.get("/api/me/skills")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_my_skills_excludes_deleted(client: AsyncClient):
    """技能列表排除已删除的"""
    agent_id, api_key = await _create_active_agent(client, "user7")

    await _insert_skill(agent_id, "正常技能")
    skill_id = await _insert_skill(agent_id, "已删除技能")

    db = await get_db()
    await db.execute(
        "UPDATE skills SET deleted_at = '2026-01-01T00:00:00' WHERE skill_id = ?",
        (skill_id,),
    )
    await db.commit()

    resp = await client.get("/api/me/skills", headers=_auth_header(api_key))
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["name"] == "正常技能"


# --- GET /api/me/downloads ---


@pytest.mark.anyio
async def test_my_downloads(client: AsyncClient):
    """AC-4: 我的下载记录"""
    agent_id, api_key = await _create_active_agent(client, "user8")
    skill_id = await _insert_skill(agent_id, "被下载的技能")

    download_id = await _insert_download(agent_id, skill_id)

    resp = await client.get("/api/me/downloads", headers=_auth_header(api_key))
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["id"] == download_id
    assert data["data"]["items"][0]["skill"]["name"] == "被下载的技能"


@pytest.mark.anyio
async def test_my_downloads_pagination(client: AsyncClient):
    """下载记录分页"""
    agent_id, api_key = await _create_active_agent(client, "user9")
    skill_id = await _insert_skill(agent_id, "技能")

    for i in range(5):
        await _insert_download(agent_id, skill_id)

    resp = await client.get("/api/me/downloads?page=1&limit=3", headers=_auth_header(api_key))
    data = resp.json()
    assert data["data"]["total"] == 5
    assert len(data["data"]["items"]) == 3


@pytest.mark.anyio
async def test_my_downloads_requires_auth(client: AsyncClient):
    """GET /api/me/downloads 需要 API Key"""
    resp = await client.get("/api/me/downloads")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_my_downloads_empty(client: AsyncClient):
    """无下载记录时返回空列表"""
    _, api_key = await _create_active_agent(client, "user10")

    resp = await client.get("/api/me/downloads", headers=_auth_header(api_key))
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 0
    assert data["data"]["items"] == []


# --- GET /api/rankings ---


@pytest.mark.anyio
async def test_rankings(client: AsyncClient):
    """AC-5: 排行榜无需认证"""
    agent_id, api_key = await _create_active_agent(client, "ranker1")
    db = await get_db()
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 500, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings")
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]["items"]) >= 1
    assert data["data"]["items"][0]["username"] == "ranker1"
    assert data["data"]["items"][0]["balance"] == 500
    assert data["data"]["items"][0]["level"] == "A2-2"
    assert data["data"]["items"][0]["rank"] == 1


@pytest.mark.anyio
async def test_rankings_no_auth(client: AsyncClient):
    """AC-5: 排行榜无需认证"""
    resp = await client.get("/api/rankings")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_rankings_sorted_by_balance(client: AsyncClient):
    """排行榜按余额降序"""
    db = await get_db()
    now = "2026-01-01T00:00:00"

    # Create 3 agents with different balances
    for i, balance in enumerate([300, 100, 500]):
        username = f"sorter{i}"
        agent_id, _ = await _create_active_agent(client, username)
        await db.execute(
            "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(agent_id) DO UPDATE SET balance = ?",
            (str(uuid.uuid4()), agent_id, balance, now, now, balance),
        )
        await db.commit()

    resp = await client.get("/api/rankings")
    data = resp.json()
    items = data["data"]["items"]
    assert items[0]["balance"] >= items[1]["balance"]
    assert items[1]["balance"] >= items[2]["balance"]
    assert items[0]["rank"] == 1


@pytest.mark.anyio
async def test_rankings_empty(client: AsyncClient):
    """无数据时返回空排行榜"""
    resp = await client.get("/api/rankings")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["items"] == []


@pytest.mark.anyio
async def test_rankings_with_level(client: AsyncClient):
    """排行榜包含等级信息"""
    agent_id, _ = await _create_active_agent(client, "highranker")
    db = await get_db()
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 12000, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings")
    data = resp.json()
    assert data["data"]["items"][0]["level"] == "A4-1"
