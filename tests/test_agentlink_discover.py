"""US-101 AgentLink 发现笔友与喜欢/跳过测试"""
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


async def _create_active_agent_with_profile(
    username: str = None, mbti: str = ""
) -> tuple[str, str]:
    """创建已激活的 agent 并附带 penpal profile，返回 (agent_id, api_key)"""
    agent_id, api_key = await _create_active_agent(username)
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO penpal_profiles
           (id, agent_id, bio, mbti, looking_for, interests, created_at, updated_at)
           VALUES (?, ?, '我是' || ?, ?, '', '', ?, NULL)""",
        (profile_id, agent_id, username or "user", mbti, now),
    )
    await db.commit()
    return agent_id, api_key


@pytest.mark.anyio
async def test_discover_returns_one_agent():
    """GET /discover 随机返回一个未操作过的 agent"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent_with_profile("target", "INTP")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/discover",
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["agent_id"] == target_id
    assert data["data"]["username"] == "target"
    assert data["data"]["nickname"] == "TestNick"
    assert "avatar_url" in data["data"]
    assert "bio" in data["data"]
    assert data["data"]["mbti"] == "INTP"


@pytest.mark.anyio
async def test_discover_needs_auth():
    """GET /discover 需要 API Key"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/agentlink/discover")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_discover_excludes_self():
    """发现笔友排除自己"""
    my_id, my_key = await _create_active_agent("me")
    # 只有自己一个 agent
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/discover",
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] is None


@pytest.mark.anyio
async def test_discover_excludes_liked():
    """发现笔友排除已喜欢的 agent"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    # 喜欢目标
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), my_id, target_id, now),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/discover",
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] is None


@pytest.mark.anyio
async def test_discover_excludes_passed():
    """发现笔友排除已跳过的 agent"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    # 跳过目标
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'pass', ?)""",
        (str(uuid.uuid4()), my_id, target_id, now),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/discover",
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] is None


@pytest.mark.anyio
async def test_discover_empty_when_all_operated():
    """所有 agent 都已操作过时返回空"""
    my_id, my_key = await _create_active_agent("me")
    t1, _ = await _create_active_agent("t1")
    t2, _ = await _create_active_agent("t2")

    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (str(uuid.uuid4()), my_id, t1, now),
    )
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'pass', ?)""",
        (str(uuid.uuid4()), my_id, t2, now),
    )
    await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/discover",
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] is None


@pytest.mark.anyio
async def test_like_penpal():
    """POST /discover/like 喜欢某人"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["liked"] is True
    assert data["data"]["matched"] is False


@pytest.mark.anyio
async def test_like_creates_match():
    """双向喜欢自动创建 match 记录"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, a2_key = await _create_active_agent("a2")

    # a2 先喜欢 a1
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": a1_id},
            headers={"agent-auth-api-key": a2_key},
        )

        # a1 再喜欢 a2 → 应该触发匹配
        resp = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": a2_id},
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["matched"] is True

    # 验证 matches 表有记录
    db = await get_db()
    cursor = await db.execute("SELECT * FROM matches")
    rows = await cursor.fetchall()
    assert len(rows) == 1


@pytest.mark.anyio
async def test_like_self_error():
    """不能喜欢自己"""
    my_id, my_key = await _create_active_agent("me")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": my_id},
            headers={"agent-auth-api-key": my_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert "自己" in data["message"]


@pytest.mark.anyio
async def test_like_duplicate_error():
    """重复喜欢同一 agent 返回错误"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # 第一次喜欢
        resp1 = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
        assert resp1.json()["success"] is True

        # 第二次重复喜欢
        resp2 = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
    assert resp2.json()["success"] is False
    assert resp2.json()["error"] == "duplicate"


@pytest.mark.anyio
async def test_like_nonexistent_target():
    """喜欢不存在的 agent 返回错误"""
    my_id, my_key = await _create_active_agent("me")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": str(uuid.uuid4())},
            headers={"agent-auth-api-key": my_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_pass_penpal():
    """POST /discover/pass 跳过某人"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/pass",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["passed"] is True


@pytest.mark.anyio
async def test_pass_self_error():
    """不能跳过自己"""
    my_id, my_key = await _create_active_agent("me")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/pass",
            json={"target_id": my_id},
            headers={"agent-auth-api-key": my_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert "自己" in data["message"]


@pytest.mark.anyio
async def test_pass_duplicate_error():
    """重复跳过同一 agent 返回错误（先 like 再 pass 也报错）"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # 先喜欢
        await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
        # 再跳过同一人 → 应报错
        resp = await ac.post(
            "/api/agentlink/discover/pass",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.json()["success"] is False
    assert resp.json()["error"] == "duplicate"


@pytest.mark.anyio
async def test_pass_then_like_same_target():
    """先 pass 再 like 同一目标也报错"""
    my_id, my_key = await _create_active_agent("me")
    target_id, _ = await _create_active_agent("target")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post(
            "/api/agentlink/discover/pass",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
        resp = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": target_id},
            headers={"agent-auth-api-key": my_key},
        )
    assert resp.json()["success"] is False
    assert resp.json()["error"] == "duplicate"


@pytest.mark.anyio
async def test_like_needs_auth():
    """POST /discover/like 需要 API Key"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_pass_needs_auth():
    """POST /discover/pass 需要 API Key"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/agentlink/discover/pass",
            json={"target_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_match_not_created_for_pass():
    """pass 不会触发匹配（即使对方喜欢了自己）"""
    a1_id, a1_key = await _create_active_agent("a1")
    a2_id, a2_key = await _create_active_agent("a2")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # a2 喜欢 a1
        await ac.post(
            "/api/agentlink/discover/like",
            json={"target_id": a1_id},
            headers={"agent-auth-api-key": a2_key},
        )
        # a1 跳过 a2 → 不应匹配
        resp = await ac.post(
            "/api/agentlink/discover/pass",
            json={"target_id": a2_id},
            headers={"agent-auth-api-key": a1_key},
        )
    data = resp.json()
    assert data["success"] is True

    # matches 表应为空
    db = await get_db()
    cursor = await db.execute("SELECT * FROM matches")
    rows = await cursor.fetchall()
    assert len(rows) == 0
