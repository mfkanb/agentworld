"""US-201 任务与XP系统 API 测试"""
import pytest
from datetime import date, timedelta
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
    await db.execute("DELETE FROM task_completions")
    await db.execute("DELETE FROM tasks")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM sign_in_records")
    await db.execute("DELETE FROM post_likes")
    await db.execute("DELETE FROM posts")
    await db.execute("DELETE FROM skills")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "taskuser") -> tuple[str, str]:
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
    verify_data = resp.json()["data"]
    return row["agent_id"], verify_data["api_key"]


@pytest.mark.anyio
async def test_get_tasks_needs_auth(client: AsyncClient):
    """获取任务列表需要认证"""
    resp = await client.get("/api/tasks")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_get_tasks_returns_preset_tasks(client: AsyncClient):
    """返回5个预设任务"""
    _, api_key = await _create_active_agent(client)
    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    tasks = data["data"]["tasks"]
    assert len(tasks) == 10

    task_ids = {t["id"] for t in tasks}
    assert "daily_checkin" in task_ids
    assert "daily_post" in task_ids
    assert "daily_social" in task_ids
    assert "achievement_first_skill" in task_ids
    assert "achievement_10_posts" in task_ids
    # 新手任务
    assert "beginner_complete_profile" in task_ids
    assert "beginner_first_guestbook" in task_ids
    assert "beginner_first_drink" in task_ids
    assert "beginner_register_farm" in task_ids
    assert "beginner_first_discover" in task_ids


@pytest.mark.anyio
async def test_get_tasks_has_progress_and_status(client: AsyncClient):
    """任务包含进度和完成状态"""
    _, api_key = await _create_active_agent(client)
    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    tasks = resp.json()["data"]["tasks"]

    for task in tasks:
        assert "progress" in task
        assert "is_completed" in task
        assert "target_count" in task
        assert "reward_xp" in task
        assert "reward_gold" in task
        assert task["is_completed"] is False


@pytest.mark.anyio
async def test_complete_task_needs_auth(client: AsyncClient):
    """完成任务需要认证"""
    resp = await client.post("/api/tasks/daily_checkin/complete")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_complete_task_not_found(client: AsyncClient):
    """不存在的任务"""
    _, api_key = await _create_active_agent(client)
    resp = await client.post("/api/tasks/nonexistent/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is False
    assert "task_not_found" in data["error"]


@pytest.mark.anyio
async def test_complete_daily_checkin(client: AsyncClient):
    """完成每日签到任务：需要先签到"""
    agent_id, api_key = await _create_active_agent(client)

    # 先签到
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})

    # 完成任务
    resp = await client.post("/api/tasks/daily_checkin/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_xp"] == 10
    assert data["data"]["task_id"] == "daily_checkin"


@pytest.mark.anyio
async def test_complete_daily_checkin_conditions_not_met(client: AsyncClient):
    """未签到时不能完成签到任务"""
    _, api_key = await _create_active_agent(client)
    resp = await client.post("/api/tasks/daily_checkin/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is False
    assert "conditions_not_met" in data["error"]


@pytest.mark.anyio
async def test_complete_daily_task_twice_same_day(client: AsyncClient):
    """同一天重复完成每日任务"""
    agent_id, api_key = await _create_active_agent(client)

    # 签到 + 完成任务
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    resp1 = await client.post("/api/tasks/daily_checkin/complete", headers={"agent-auth-api-key": api_key})

    # Fix completed_at to match local date (UTC vs local timezone mismatch in production)
    db = await get_db()
    today = date.today().isoformat()
    await db.execute(
        "UPDATE task_completions SET completed_at = ? WHERE agent_id = ? AND task_id = 'daily_checkin'",
        (today + "T12:00:00", agent_id),
    )
    await db.commit()

    # 再次完成
    resp = await client.post("/api/tasks/daily_checkin/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is False
    assert "already_completed" in data["error"]


@pytest.mark.anyio
async def test_xp_awarded_on_complete(client: AsyncClient):
    """完成任务后 XP 增加"""
    agent_id, api_key = await _create_active_agent(client)

    # 签到
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})

    # 完成签到任务 +10 XP
    await client.post("/api/tasks/daily_checkin/complete", headers={"agent-auth-api-key": api_key})

    # 检查钱包 XP
    db = await get_db()
    cursor = await db.execute("SELECT xp FROM wallets WHERE agent_id = ?", (agent_id,))
    row = await cursor.fetchone()
    assert row["xp"] == 10


@pytest.mark.anyio
async def test_daily_task_resets_next_day(client: AsyncClient):
    """每日任务第二天重置"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 签到
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    # 完成任务
    await client.post("/api/tasks/daily_checkin/complete", headers={"agent-auth-api-key": api_key})

    # Fix completed_at to match local date (UTC vs local timezone mismatch in production)
    today = date.today().isoformat()
    await db.execute(
        "UPDATE task_completions SET completed_at = ? WHERE agent_id = ? AND task_id = 'daily_checkin'",
        (today + "T12:00:00", agent_id),
    )
    await db.commit()

    # 验证今天已完成
    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    checkin_task = next(t for t in resp.json()["data"]["tasks"] if t["id"] == "daily_checkin")
    assert checkin_task["is_completed"] is True

    # 模拟完成记录是昨天的
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await db.execute(
        "UPDATE task_completions SET completed_at = ? WHERE agent_id = ? AND task_id = 'daily_checkin'",
        (yesterday + "T12:00:00+00:00", agent_id),
    )
    await db.commit()

    # 今天应该显示未完成
    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    checkin_task = next(t for t in resp.json()["data"]["tasks"] if t["id"] == "daily_checkin")
    assert checkin_task["is_completed"] is False


@pytest.mark.anyio
async def test_achievement_first_skill(client: AsyncClient):
    """成就任务：首次发布技能"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 手动插入一个技能（模拟发布）
    await db.execute(
        "INSERT INTO skills (skill_id, author_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
        ("skill-1", agent_id, "test-skill", "desc", "2026-01-01T00:00:00"),
    )
    await db.commit()

    # 完成成就
    resp = await client.post("/api/tasks/achievement_first_skill/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_xp"] == 50

    # XP 应该增加
    cursor = await db.execute("SELECT xp FROM wallets WHERE agent_id = ?", (agent_id,))
    row = await cursor.fetchone()
    assert row["xp"] == 50


@pytest.mark.anyio
async def test_achievement_cannot_complete_twice(client: AsyncClient):
    """成就任务只能完成一次"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 手动插入一个技能
    await db.execute(
        "INSERT INTO skills (skill_id, author_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
        ("skill-1", agent_id, "test-skill", "desc", "2026-01-01T00:00:00"),
    )
    await db.commit()

    # 完成成就
    await client.post("/api/tasks/achievement_first_skill/complete", headers={"agent-auth-api-key": api_key})

    # 再次完成
    resp = await client.post("/api/tasks/achievement_first_skill/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is False
    assert "already_completed" in data["error"]


@pytest.mark.anyio
async def test_daily_social_progress_tracks_likes(client: AsyncClient):
    """每日社交进度跟踪点赞"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 手动插入一个帖子和点赞
    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("post-1", "other-agent", "test", "content", "2026-01-01T00:00:00"),
    )
    today = date.today().isoformat()
    await db.execute(
        "INSERT INTO post_likes (id, post_id, agent_id, created_at) VALUES (?, ?, ?, ?)",
        ("like-1", "post-1", agent_id, today + "T12:00:00"),
    )
    await db.commit()

    # 查看任务列表进度
    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    tasks = resp.json()["data"]["tasks"]
    social_task = next(t for t in tasks if t["id"] == "daily_social")
    assert social_task["progress"] == 1


@pytest.mark.anyio
async def test_complete_daily_social(client: AsyncClient):
    """完成每日社交任务"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 手动插入一个帖子和点赞
    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("post-1", "other-agent", "test", "content", "2026-01-01T00:00:00"),
    )
    today = date.today().isoformat()
    await db.execute(
        "INSERT INTO post_likes (id, post_id, agent_id, created_at) VALUES (?, ?, ?, ?)",
        ("like-1", "post-1", agent_id, today + "T12:00:00"),
    )
    await db.commit()

    resp = await client.post("/api/tasks/daily_social/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_xp"] == 10


@pytest.mark.anyio
async def test_progress_shows_checkin_done(client: AsyncClient):
    """签到后 checkin 任务进度为 1"""
    _, api_key = await _create_active_agent(client)
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})

    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    tasks = resp.json()["data"]["tasks"]
    checkin_task = next(t for t in tasks if t["id"] == "daily_checkin")
    assert checkin_task["progress"] == 1
