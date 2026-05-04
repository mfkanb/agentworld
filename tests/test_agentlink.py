"""US-100 AgentLink 笔友 Profile 管理测试"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.services.database import get_db


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM penpal_profiles")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield
    # 清理
    db = await get_db()
    await db.execute("DELETE FROM penpal_profiles")
    await db.execute("DELETE FROM agents")
    await db.commit()


async def _create_active_agent(username: str = None) -> tuple[str, str]:
    """创建已激活的 agent，返回 (agent_id, api_key)"""
    db = await get_db()
    agent_id = str(uuid.uuid4())
    api_key = f"agent-world-test-{uuid.uuid4().hex[:24]}"
    uname = username or f"testuser_{uuid.uuid4().hex[:8]}"
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO agents
           (agent_id, username, nickname, bio, is_active, api_key, created_at)
           VALUES (?, ?, 'TestNick', '', 1, ?, ?)""",
        (agent_id, uname, api_key, now),
    )
    await db.commit()
    return agent_id, api_key


@pytest.mark.anyio
async def test_tables_created():
    """验证 penpal_profiles, likes, matches 表已创建"""
    db = await get_db()
    for table in ["penpal_profiles", "likes", "matches"]:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        assert await cursor.fetchone() is not None, f"表 {table} 不存在"


@pytest.mark.anyio
async def test_get_profile_me_auto_create():
    """首次 GET /profile/me 自动创建空 profile"""
    agent_id, api_key = await _create_active_agent()
    async with AsyncClient(
        transport=ASGITransport(app=None), base_url="http://test"
    ) as ac:
        from src.main import app
        ac._transport.app = app
        resp = await ac.get(
            "/api/agentlink/profile/me",
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["bio"] == ""
    assert data["data"]["mbti"] == ""
    assert "created_at" in data["data"]


@pytest.mark.anyio
async def test_get_profile_me_needs_auth():
    """GET /profile/me 需要 API Key"""
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/agentlink/profile/me")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_update_penpal_profile():
    """PATCH /profile 更新 bio 和 mbti"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.patch(
            "/api/agentlink/profile",
            json={"bio": "你好，我是AI笔友", "mbti": "INTP"},
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["bio"] == "你好，我是AI笔友"
    assert data["data"]["mbti"] == "INTP"
    assert data["data"]["updated_at"] is not None


@pytest.mark.anyio
async def test_update_profile_bio_required():
    """PATCH /profile bio 必填"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.patch(
            "/api/agentlink/profile",
            json={"mbti": "ENFP"},
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_profile_bio_max_length():
    """bio 超过 500 字符返回 422"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.patch(
            "/api/agentlink/profile",
            json={"bio": "x" * 501},
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_profile_invalid_mbti():
    """无效 mbti 格式返回 422"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.patch(
            "/api/agentlink/profile",
            json={"bio": "test", "mbti": "INVALID"},
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_profile_mbti_case_insensitive():
    """mbti 大小写不敏感，自动转大写"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.patch(
            "/api/agentlink/profile",
            json={"bio": "test", "mbti": "intp"},
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["mbti"] == "INTP"


@pytest.mark.anyio
async def test_get_other_profile():
    """GET /profile/{username} 查看他人笔友 profile"""
    agent_id, api_key = await _create_active_agent("viewer")
    target_id, _ = await _create_active_agent("target")

    # 先给 target 更新 profile
    db = await get_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO penpal_profiles
           (id, agent_id, bio, mbti, looking_for, interests, created_at, updated_at)
           VALUES (?, ?, '我是目标', 'ENFP', '', '', ?, NULL)""",
        (profile_id, target_id, now),
    )
    await db.commit()

    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/profile/target",
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["bio"] == "我是目标"
    assert data["data"]["mbti"] == "ENFP"
    assert data["data"]["username"] == "target"


@pytest.mark.anyio
async def test_get_other_profile_not_found():
    """GET /profile/{username} 用户不存在"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/profile/nonexistent",
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


@pytest.mark.anyio
async def test_get_other_profile_needs_auth():
    """GET /profile/{username} 需要 API Key"""
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/agentlink/profile/someone")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_update_then_get_profile():
    """更新后再查看自己的 profile 数据一致"""
    agent_id, api_key = await _create_active_agent()
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # 更新
        await ac.patch(
            "/api/agentlink/profile",
            json={"bio": "Updated bio"},
            headers={"agent-auth-api-key": api_key},
        )
        # 查看
        resp = await ac.get(
            "/api/agentlink/profile/me",
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["bio"] == "Updated bio"


@pytest.mark.anyio
async def test_get_other_profile_empty():
    """查看未创建 profile 的用户返回空数据"""
    agent_id, api_key = await _create_active_agent("viewer")
    target_id, _ = await _create_active_agent("no_profile")
    from src.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get(
            "/api/agentlink/profile/no_profile",
            headers={"agent-auth-api-key": api_key},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["bio"] == ""
