"""US-012 虾评-技能下载与收藏测试"""
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
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM favorites")
    await db.execute("DELETE FROM downloads")
    await db.execute("DELETE FROM skills")
    await db.execute("DELETE FROM wallets")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "dlauthor") -> tuple[str, str]:
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


async def _create_skill(client: AsyncClient, api_key: str, name: str = "test-skill") -> str:
    """创建技能并返回 skill_id"""
    resp = await client.post(
        "/api/skills",
        json={"name": name, "description": "A test skill", "category": "tools"},
        headers=_auth_header(api_key),
    )
    return resp.json()["data"]["id"]


# --- GET /api/skills/{id}/download ---

@pytest.mark.anyio
async def test_download_trial_skill_free(client: AsyncClient):
    """试用版(draft)下载免费"""
    _, api_key = await _create_active_agent(client, "dluser1")
    skill_id = await _create_skill(client, api_key, "trial-skill")

    resp = await client.get(
        f"/api/skills/{skill_id}/download",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["is_trial"] is True
    assert data["data"]["cost"] == 0


@pytest.mark.anyio
async def test_download_formal_skill_costs_2(client: AsyncClient):
    """正式版下载-2虾米"""
    # Create author with some xiami (from publishing)
    author_id, author_key = await _create_active_agent(client, "author_formal")
    skill_id = await _create_skill(client, author_key, "formal-skill")

    # Manually update skill to formal version
    db = await get_db()
    await db.execute(
        "UPDATE skills SET version = '1.0', status = 'published' WHERE skill_id = ?",
        (skill_id,),
    )
    await db.commit()

    # Create a downloader with balance
    dl_id, dl_key = await _create_active_agent(client, "downloader1")
    # Give downloader some xiami
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 10, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = balance + 10",
        (str(uuid.uuid4()), dl_id, datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

    resp = await client.get(
        f"/api/skills/{skill_id}/download",
        headers=_auth_header(dl_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["is_trial"] is False
    assert data["data"]["cost"] == 2

    # Check balance deducted
    cursor = await db.execute("SELECT balance FROM wallets WHERE agent_id = ?", (dl_id,))
    # downloader got 10 from manual insert, no skill publish bonus
    row = await cursor.fetchone()
    assert row["balance"] == 58  # 50 (initial) + 10 (manual) - 2 (cost)


@pytest.mark.anyio
async def test_download_insufficient_balance(client: AsyncClient):
    """虾米不足无法下载正式版"""
    _, author_key = await _create_active_agent(client, "author_poor")
    skill_id = await _create_skill(client, author_key, "expensive-skill")

    db = await get_db()
    await db.execute(
        "UPDATE skills SET version = '2.0', status = 'published' WHERE skill_id = ?",
        (skill_id,),
    )
    await db.commit()

    # New user with no balance (drain the initial 50 from verify)
    _, poor_key = await _create_active_agent(client, "poordownloader")
    db = await get_db()
    cursor = await db.execute("SELECT agent_id FROM agents WHERE username = 'poordownloader'")
    poor_row = await cursor.fetchone()
    await db.execute("UPDATE wallets SET balance = 0 WHERE agent_id = ?", (poor_row["agent_id"],))
    await db.commit()

    resp = await client.get(
        f"/api/skills/{skill_id}/download",
        headers=_auth_header(poor_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert "insufficient" in data["error"] or "不足" in data["message"]


@pytest.mark.anyio
async def test_download_increments_count(client: AsyncClient):
    """下载计数+1"""
    _, api_key = await _create_active_agent(client, "dlcounter")
    skill_id = await _create_skill(client, api_key, "counted-skill")

    resp = await client.get(
        f"/api/skills/{skill_id}/download",
        headers=_auth_header(api_key),
    )
    assert resp.json()["success"] is True

    db = await get_db()
    cursor = await db.execute("SELECT downloads FROM skills WHERE skill_id = ?", (skill_id,))
    row = await cursor.fetchone()
    assert row["downloads"] == 1


@pytest.mark.anyio
async def test_download_requires_auth(client: AsyncClient):
    """下载需要 API Key"""
    resp = await client.get(f"/api/skills/{str(uuid.uuid4())}/download")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_download_not_found(client: AsyncClient):
    """下载不存在的技能"""
    _, api_key = await _create_active_agent(client, "dlnf")
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/skills/{fake_id}/download",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


# --- POST /api/skills/{id}/favorite ---

@pytest.mark.anyio
async def test_add_favorite_success(client: AsyncClient):
    """收藏成功"""
    _, api_key = await _create_active_agent(client, "favuser1")
    skill_id = await _create_skill(client, api_key, "fav-skill")

    resp = await client.post(
        f"/api/skills/{skill_id}/favorite",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["skill_id"] == skill_id


@pytest.mark.anyio
async def test_add_favorite_already_exists(client: AsyncClient):
    """重复收藏返回错误"""
    _, api_key = await _create_active_agent(client, "favuser2")
    skill_id = await _create_skill(client, api_key, "dup-fav")

    await client.post(f"/api/skills/{skill_id}/favorite", headers=_auth_header(api_key))
    resp = await client.post(
        f"/api/skills/{skill_id}/favorite",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert "already" in data["error"]


@pytest.mark.anyio
async def test_add_favorite_skill_not_found(client: AsyncClient):
    """收藏不存在的技能"""
    _, api_key = await _create_active_agent(client, "favnf")
    resp = await client.post(
        f"/api/skills/{str(uuid.uuid4())}/favorite",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_add_favorite_requires_auth(client: AsyncClient):
    """收藏需要 API Key"""
    resp = await client.post(f"/api/skills/{str(uuid.uuid4())}/favorite")
    assert resp.status_code == 401


# --- DELETE /api/skills/{id}/favorite ---

@pytest.mark.anyio
async def test_remove_favorite_success(client: AsyncClient):
    """取消收藏成功"""
    _, api_key = await _create_active_agent(client, "rmfav1")
    skill_id = await _create_skill(client, api_key, "rm-skill")

    await client.post(f"/api/skills/{skill_id}/favorite", headers=_auth_header(api_key))
    resp = await client.delete(
        f"/api/skills/{skill_id}/favorite",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["skill_id"] == skill_id


@pytest.mark.anyio
async def test_remove_favorite_not_favorited(client: AsyncClient):
    """取消未收藏的技能"""
    _, api_key = await _create_active_agent(client, "rmfav2")
    skill_id = await _create_skill(client, api_key, "nf-skill")

    resp = await client.delete(
        f"/api/skills/{skill_id}/favorite",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


# --- GET /api/me/favorites ---

@pytest.mark.anyio
async def test_list_favorites_paginated(client: AsyncClient):
    """收藏列表分页"""
    _, api_key = await _create_active_agent(client, "favlist1")

    # Create 3 skills and favorite 2
    skill1 = await _create_skill(client, api_key, "fav-a")
    skill2 = await _create_skill(client, api_key, "fav-b")

    await client.post(f"/api/skills/{skill1}/favorite", headers=_auth_header(api_key))
    await client.post(f"/api/skills/{skill2}/favorite", headers=_auth_header(api_key))

    resp = await client.get(
        "/api/me/favorites",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 2
    assert len(data["data"]["items"]) == 2
    # Each item should have skill details
    assert "skill" in data["data"]["items"][0]
    assert data["data"]["items"][0]["skill"]["name"] in ("fav-a", "fav-b")


@pytest.mark.anyio
async def test_list_favorites_pagination(client: AsyncClient):
    """收藏列表分页参数"""
    _, api_key = await _create_active_agent(client, "favpage")

    # Create and favorite 3 skills
    for i in range(3):
        sid = await _create_skill(client, api_key, f"page-skill-{i}")
        await client.post(f"/api/skills/{sid}/favorite", headers=_auth_header(api_key))

    # Page 1 with limit 2
    resp = await client.get(
        "/api/me/favorites?page=1&limit=2",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["data"]["total"] == 3
    assert len(data["data"]["items"]) == 2
    assert data["data"]["page"] == 1
    assert data["data"]["limit"] == 2


@pytest.mark.anyio
async def test_list_favorites_empty(client: AsyncClient):
    """无收藏返回空列表"""
    _, api_key = await _create_active_agent(client, "favempty")

    resp = await client.get(
        "/api/me/favorites",
        headers=_auth_header(api_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 0
    assert data["data"]["items"] == []


@pytest.mark.anyio
async def test_list_favorites_requires_auth(client: AsyncClient):
    """收藏列表需要 API Key"""
    resp = await client.get("/api/me/favorites")
    assert resp.status_code == 401
