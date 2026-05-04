"""US-300 新用户初始资产与新手任务链 API 测试"""
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
    await db.execute("DELETE FROM task_completions")
    await db.execute("DELETE FROM tasks")
    await db.execute("DELETE FROM likes")
    await db.execute("DELETE FROM farms")
    await db.execute("DELETE FROM drink_sessions")
    await db.execute("DELETE FROM guestbook")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "beginner_user") -> tuple[str, str]:
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
async def test_verify_creates_wallet_with_50_balance(client: AsyncClient):
    """激活账号时自动写入50虾米初始余额"""
    agent_id, _ = await _create_active_agent(client, "walletuser")

    db = await get_db()
    cursor = await db.execute("SELECT balance FROM wallets WHERE agent_id = ?", (agent_id,))
    row = await cursor.fetchone()
    assert row is not None
    assert row["balance"] == 50


@pytest.mark.anyio
async def test_beginner_tasks_in_task_list(client: AsyncClient):
    """GET /api/tasks 包含 beginner 类型任务"""
    _, api_key = await _create_active_agent(client, "tasklistuser")

    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    tasks = data["data"]["tasks"]

    beginner_tasks = [t for t in tasks if t["task_type"] == "beginner"]
    assert len(beginner_tasks) == 5

    beginner_ids = {t["id"] for t in beginner_tasks}
    assert "beginner_complete_profile" in beginner_ids
    assert "beginner_first_guestbook" in beginner_ids
    assert "beginner_first_drink" in beginner_ids
    assert "beginner_register_farm" in beginner_ids
    assert "beginner_first_discover" in beginner_ids


@pytest.mark.anyio
async def test_beginner_tasks_shown_alongside_daily_achievement(client: AsyncClient):
    """beginner 任务和 daily/achievement 并列展示"""
    _, api_key = await _create_active_agent(client, "alltaskuser")

    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    tasks = resp.json()["data"]["tasks"]

    types = {t["task_type"] for t in tasks}
    assert "daily" in types
    assert "achievement" in types
    assert "beginner" in types


@pytest.mark.anyio
async def test_beginner_task_rewards(client: AsyncClient):
    """beginner 任务奖励正确"""
    _, api_key = await _create_active_agent(client, "rewarduser")

    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    tasks = resp.json()["data"]["tasks"]
    beginner_by_id = {t["id"]: t for t in tasks if t["task_type"] == "beginner"}

    assert beginner_by_id["beginner_complete_profile"]["reward_gold"] == 10
    assert beginner_by_id["beginner_first_guestbook"]["reward_gold"] == 10
    assert beginner_by_id["beginner_first_drink"]["reward_gold"] == 10
    assert beginner_by_id["beginner_register_farm"]["reward_gold"] == 15
    assert beginner_by_id["beginner_first_discover"]["reward_gold"] == 10


@pytest.mark.anyio
async def test_complete_beginner_profile(client: AsyncClient):
    """完成 beginner_complete_profile 任务"""
    agent_id, api_key = await _create_active_agent(client, "profiledoer")

    # 更新 profile 使 nickname 非空
    await client.put("/api/agents/profile", headers={"agent-auth-api-key": api_key}, json={"nickname": "测试"})

    resp = await client.post("/api/tasks/beginner_complete_profile/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_gold"] == 10
    assert data["data"]["task_id"] == "beginner_complete_profile"

    # 验证余额增加 50(初始) + 10(奖励) = 60
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM wallets WHERE agent_id = ?", (agent_id,))
    row = await cursor.fetchone()
    assert row["balance"] == 60


@pytest.mark.anyio
async def test_complete_beginner_guestbook(client: AsyncClient):
    """完成 beginner_first_guestbook 任务"""
    agent_id, api_key = await _create_active_agent(client, "gbdoer")
    db = await get_db()

    # 插入一条留言
    await db.execute(
        "INSERT INTO guestbook (entry_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("gb-1", agent_id, "hello", datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

    resp = await client.post("/api/tasks/beginner_first_guestbook/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_gold"] == 10


@pytest.mark.anyio
async def test_complete_beginner_drink(client: AsyncClient):
    """完成 beginner_first_drink 任务"""
    agent_id, api_key = await _create_active_agent(client, "drinkdoer")
    db = await get_db()

    # 插入一个饮酒 session
    await db.execute(
        "INSERT INTO drink_sessions (session_id, agent_id, drink_id, created_at) VALUES (?, ?, ?, ?)",
        ("ds-1", agent_id, "d-1", datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

    resp = await client.post("/api/tasks/beginner_first_drink/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_gold"] == 10


@pytest.mark.anyio
async def test_complete_beginner_farm(client: AsyncClient):
    """完成 beginner_register_farm 任务"""
    agent_id, api_key = await _create_active_agent(client, "farmdoer")
    db = await get_db()

    # 插入一个农场记录
    await db.execute(
        "INSERT INTO farms (id, agent_id, name, created_at) VALUES (?, ?, ?, ?)",
        ("farm-1", agent_id, "my farm", datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

    resp = await client.post("/api/tasks/beginner_register_farm/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_gold"] == 15


@pytest.mark.anyio
async def test_complete_beginner_discover(client: AsyncClient):
    """完成 beginner_first_discover 任务"""
    agent_id, api_key = await _create_active_agent(client, "discdoer")
    db = await get_db()

    # 插入一个 like 记录（AgentLink discover）
    await db.execute(
        "INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at) VALUES (?, ?, ?, 'like', ?)",
        ("like-1", agent_id, "other-agent", datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

    resp = await client.post("/api/tasks/beginner_first_discover/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward_gold"] == 10


@pytest.mark.anyio
async def test_beginner_task_no_daily_reset(client: AsyncClient):
    """beginner 任务不设每日重置，永久可完成一次"""
    agent_id, api_key = await _create_active_agent(client, "nodailyuser")
    db = await get_db()

    # 插入一条留言
    await db.execute(
        "INSERT INTO guestbook (entry_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
        ("gb-1", agent_id, "hello", datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()

    # 完成任务
    await client.post("/api/tasks/beginner_first_guestbook/complete", headers={"agent-auth-api-key": api_key})

    # 验证已完成
    resp = await client.get("/api/tasks", headers={"agent-auth-api-key": api_key})
    task = next(t for t in resp.json()["data"]["tasks"] if t["id"] == "beginner_first_guestbook")
    assert task["is_completed"] is True

    # 再次完成应报错
    resp = await client.post("/api/tasks/beginner_first_guestbook/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is False
    assert "already_completed" in data["error"]


@pytest.mark.anyio
async def test_beginner_task_conditions_not_met(client: AsyncClient):
    """条件不满足时不能完成 beginner 任务"""
    _, api_key = await _create_active_agent(client, "conduser")

    resp = await client.post("/api/tasks/beginner_register_farm/complete", headers={"agent-auth-api-key": api_key})
    data = resp.json()
    assert data["success"] is False
    assert "conditions_not_met" in data["error"]
