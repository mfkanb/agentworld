"""US-102 AgentLink 匹配列表与邮箱代理测试"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM likes")
    await db.execute("DELETE FROM matches")
    await db.execute("DELETE FROM penpal_profiles")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield
    db = await get_db()
    await db.execute("DELETE FROM likes")
    await db.execute("DELETE FROM matches")
    await db.execute("DELETE FROM penpal_profiles")
    await db.execute("DELETE FROM agents")
    await db.commit()


async def _create_active_agent(username: str = None) -> tuple[str, str]:
    """创建已激活的 agent，返回 (agent_id, api_key)"""
    db = await get_db()
    agent_id = str(uuid.uuid4())
    api_key = f"agent-world-test-{uuid.uuid4().hex[:24]}"
    uname = username or f"testuser_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO agents
           (agent_id, username, nickname, bio, is_active, api_key, created_at)
           VALUES (?, ?, 'TestNick', '', 1, ?, ?)""",
        (agent_id, uname, api_key, now),
    )
    await db.commit()
    return agent_id, api_key


async def _create_mutual_match(a1_id: str, a2_id: str) -> str:
    """创建双向 like 和 match 记录，返回 match_id"""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    match_id = str(uuid.uuid4())
    # 双向 like
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), a1_id, a2_id, now),
    )
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), a2_id, a1_id, now),
    )
    # match 记录
    await db.execute(
        """INSERT INTO matches (id, agent1_id, agent2_id, created_at)
           VALUES (?, ?, ?, ?)""",
        (match_id, a1_id, a2_id, now),
    )
    await db.commit()
    return match_id


# --- GET /matches ---

@pytest.mark.anyio
async def test_get_matches_returns_matched_agents():
    """GET /matches 返回互相匹配的 Agent 列表"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")
    await _create_mutual_match(a1_id, a2_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches",
            headers={"agent-auth-api-key": a1_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    match = data["data"]["matches"][0]
    assert match["username"] == "a2"
    assert match["nickname"] == "TestNick"
    assert "avatar_url" in match
    assert match["proxy_email"] == "a2@agentlink.world"
    assert "matched_at" in match


@pytest.mark.anyio
async def test_get_matches_needs_auth():
    """GET /matches 需要 API Key"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/agentlink/matches")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_matches_empty():
    """没有匹配时返回空列表"""
    a1_id, a1_key = await _create_active_agent("a1")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches",
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 0
    assert data["data"]["matches"] == []


@pytest.mark.anyio
async def test_get_matches_multiple():
    """多个匹配全部返回"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")
    a3_id, _ = await _create_active_agent("a3")
    await _create_mutual_match(a1_id, a2_id)
    await _create_mutual_match(a1_id, a3_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches",
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["data"]["total"] == 2
    usernames = {m["username"] for m in data["data"]["matches"]}
    assert usernames == {"a2", "a3"}


# --- GET /matches/pending ---

@pytest.mark.anyio
async def test_get_pending_returns_who_liked_me():
    """GET /matches/pending 返回喜欢了我但我还没操作的人"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")

    # a2 喜欢 a1，但 a1 还没操作
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), a2_id, a1_id, now),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches/pending",
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    pending = data["data"]["pending"][0]
    assert pending["username"] == "a2"
    assert pending["nickname"] == "TestNick"
    assert "avatar_url" in pending
    assert "liked_at" in pending


@pytest.mark.anyio
async def test_get_pending_needs_auth():
    """GET /matches/pending 需要 API Key"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/agentlink/matches/pending")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_pending_excludes_already_operated():
    """已经操作过的人不出现在 pending 中"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")

    # a2 喜欢 a1
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), a2_id, a1_id, now),
    )
    # a1 也操作了 a2（like 或 pass）
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), a1_id, a2_id, now),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches/pending",
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["data"]["total"] == 0
    assert data["data"]["pending"] == []


@pytest.mark.anyio
async def test_get_pending_excludes_pass_action():
    """pass 操作的人不出现在 pending 中（只看 action='like' 的）"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")

    # a2 跳过 a1 → 不应出现在 pending
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'pass', ?)""",
        (str(uuid.uuid4()), a2_id, a1_id, now),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches/pending",
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["data"]["total"] == 0


# --- DELETE /matches/{id} ---

@pytest.mark.anyio
async def test_unmatch_success():
    """DELETE /matches/{id} 成功解除匹配"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")
    match_id = await _create_mutual_match(a1_id, a2_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete(
            f"/api/agentlink/matches/{match_id}",
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["unmatched"] is True

    # 验证 matches 表中已无该记录
    db = await get_db()
    cursor = await db.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    assert await cursor.fetchone() is None


@pytest.mark.anyio
async def test_unmatch_other_side():
    """对方也可以解除匹配"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, a2_key = await _create_active_agent("a2")
    match_id = await _create_mutual_match(a1_id, a2_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete(
            f"/api/agentlink/matches/{match_id}",
            headers={"agent-auth-api-key": a2_key},
        )
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_unmatch_not_found():
    """删除不存在的匹配返回错误"""
    _, my_key = await _create_active_agent("me")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete(
            f"/api/agentlink/matches/{str(uuid.uuid4())}",
            headers={"agent-auth-api-key": my_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_unmatch_forbidden():
    """不能解除他人的匹配"""
    a1_id, _ = await _create_active_agent("a1")
    a2_id, _ = await _create_active_agent("a2")
    a3_id, a3_key = await _create_active_agent("a3")
    match_id = await _create_mutual_match(a1_id, a2_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete(
            f"/api/agentlink/matches/{match_id}",
            headers={"agent-auth-api-key": a3_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "forbidden"


@pytest.mark.anyio
async def test_unmatch_needs_auth():
    """DELETE /matches/{id} 需要 API Key"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.delete(f"/api/agentlink/matches/{str(uuid.uuid4())}")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_proxy_email_format():
    """proxy_email 格式为 {username}@agentlink.world"""
    a1_id, a1_key = await _create_active_agent("alice")
    a2_id, _ = await _create_active_agent("bob")
    await _create_mutual_match(a1_id, a2_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches",
            headers={"agent-auth-api-key": a1_key},
        )
    match = resp.json()["data"]["matches"][0]
    assert match["proxy_email"] == "bob@agentlink.world"

    # bob 视角看到 alice 的 proxy_email
    db = await get_db()
    cursor = await db.execute(
        "SELECT api_key FROM agents WHERE agent_id = ?", (a2_id,)
    )
    row = await cursor.fetchone()
    bob_key = row["api_key"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/matches",
            headers={"agent-auth-api-key": bob_key},
        )
    match = resp.json()["data"]["matches"][0]
    assert match["proxy_email"] == "alice@agentlink.world"
