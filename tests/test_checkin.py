"""US-200 积分签到系统 API 测试"""
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
    await db.execute("DELETE FROM sign_in_records")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "checkinuser") -> tuple[str, str]:
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
async def test_first_checkin(client: AsyncClient):
    """首次签到：+5 虾米"""
    _, api_key = await _create_active_agent(client)
    resp = await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["streak_days"] == 1
    assert data["data"]["reward"] == 5
    assert data["data"]["bonus"] == 0


@pytest.mark.anyio
async def test_checkin_duplicate(client: AsyncClient):
    """同一天重复签到返回错误"""
    _, api_key = await _create_active_agent(client)
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    resp = await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "already_checked_in" in data["error"]


@pytest.mark.anyio
async def test_checkin_adds_xfund(client: AsyncClient):
    """签到后虾米余额增加"""
    _, api_key = await _create_active_agent(client)
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})

    # 检查钱包余额
    resp = await client.get("/api/auth/me", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["balance"] == 55


@pytest.mark.anyio
async def test_checkin_needs_auth(client: AsyncClient):
    """签到需要 API Key"""
    resp = await client.post("/api/checkin")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_checkin_status(client: AsyncClient):
    """签到状态查询"""
    _, api_key = await _create_active_agent(client)

    # 未签到时
    resp = await client.get("/api/checkin/status", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["checked_in_today"] is False
    assert data["streak_days"] == 0
    assert data["total_checkins"] == 0

    # 签到后
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    resp = await client.get("/api/checkin/status", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["checked_in_today"] is True
    assert data["streak_days"] == 1
    assert data["total_checkins"] == 1


@pytest.mark.anyio
async def test_checkin_streak_2_days(client: AsyncClient):
    """连续2天签到额外+2"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 模拟昨天已签到
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) VALUES (?, ?, 'main', ?, 1, 5, ?)",
        ("test-yesterday", agent_id, yesterday, yesterday + "T00:00:00"),
    )
    await db.commit()

    # 今天签到
    resp = await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["streak_days"] == 2
    assert data["reward"] == 7  # 5 base + 2 bonus
    assert data["bonus"] == 2


@pytest.mark.anyio
async def test_checkin_streak_3_days(client: AsyncClient):
    """连续3天签到额外+3"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) VALUES (?, ?, 'main', ?, 2, 7, ?)",
        ("test-yesterday", agent_id, yesterday, yesterday + "T00:00:00"),
    )
    await db.commit()

    resp = await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["streak_days"] == 3
    assert data["reward"] == 8  # 5 base + 3 bonus


@pytest.mark.anyio
async def test_checkin_streak_7_days(client: AsyncClient):
    """连续7天签到额外+5"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) VALUES (?, ?, 'main', ?, 6, 10, ?)",
        ("test-yesterday", agent_id, yesterday, yesterday + "T00:00:00"),
    )
    await db.commit()

    resp = await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["streak_days"] == 7
    assert data["reward"] == 10  # 5 base + 5 bonus


@pytest.mark.anyio
async def test_checkin_streak_broken(client: AsyncClient):
    """断签后重新开始"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 2天前签到的记录（昨天没签，连续中断）
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) VALUES (?, ?, 'main', ?, 5, 10, ?)",
        ("test-2daysago", agent_id, two_days_ago, two_days_ago + "T00:00:00"),
    )
    await db.commit()

    resp = await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["streak_days"] == 1  # 连续中断，重新开始
    assert data["reward"] == 5


@pytest.mark.anyio
async def test_checkin_history(client: AsyncClient):
    """签到历史分页"""
    agent_id, api_key = await _create_active_agent(client)
    db = await get_db()

    # 插入一些历史记录
    for i in range(5):
        d = (date.today() - timedelta(days=i)).isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) VALUES (?, ?, 'main', ?, ?, 5, ?)",
            (f"hist-{i}", agent_id, d, 5 - i, d + "T00:00:00"),
        )
    await db.commit()

    resp = await client.get("/api/checkin/history?page=1&limit=3", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["records"]) == 3
    assert data["page"] == 1
    assert data["limit"] == 3


@pytest.mark.anyio
async def test_checkin_history_needs_auth(client: AsyncClient):
    """签到历史需要认证"""
    resp = await client.get("/api/checkin/history")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_checkin_status_needs_auth(client: AsyncClient):
    """签到状态需要认证"""
    resp = await client.get("/api/checkin/status")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_checkin_next_reward_preview(client: AsyncClient):
    """下次奖励预览"""
    _, api_key = await _create_active_agent(client)
    db = await get_db()

    # 未签到，streak=0，下次 streak=1，无 bonus
    resp = await client.get("/api/checkin/status", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    assert data["next_reward"] == 5  # base only

    # 签到后 streak=1
    await client.post("/api/checkin", headers={"agent-auth-api-key": api_key})
    resp = await client.get("/api/checkin/status", headers={"agent-auth-api-key": api_key})
    data = resp.json()["data"]
    # next_streak = 2, bonus = 2, next_reward = 7
    assert data["next_reward"] == 7
