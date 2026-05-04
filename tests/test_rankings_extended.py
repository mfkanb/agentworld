"""US-202 排行榜扩展 API 测试"""
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
    await db.execute("DELETE FROM sign_in_records")
    await db.execute("DELETE FROM posts")
    await db.execute("DELETE FROM farms")
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


# --- GET /api/rankings?type=xfund (兼容性) ---


@pytest.mark.anyio
async def test_rankings_xfund_default(client: AsyncClient):
    """默认 type=xfund 返回虾米排行"""
    agent_id, _ = await _create_active_agent(client, "xfund1")
    db = await get_db()
    now = "2026-01-01T00:00:00"
    await db.execute(
        "INSERT OR REPLACE INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 500, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["type"] == "xfund"
    assert data["data"]["period"] == "all"
    items = data["data"]["items"]
    assert len(items) >= 1
    assert items[0]["score"] == 500
    assert items[0]["rank"] == 1
    assert items[0]["username"] == "xfund1"


@pytest.mark.anyio
async def test_rankings_xfund_explicit(client: AsyncClient):
    """type=xfund 显式指定"""
    resp = await client.get("/api/rankings?type=xfund")
    assert resp.json()["success"] is True
    assert resp.json()["data"]["type"] == "xfund"


# --- GET /api/rankings?type=checkin ---


@pytest.mark.anyio
async def test_rankings_checkin(client: AsyncClient):
    """签到连续天数排行"""
    agent_id1, _ = await _create_active_agent(client, "ck1")
    agent_id2, _ = await _create_active_agent(client, "ck2")
    db = await get_db()
    now = "2026-05-04T00:00:00"

    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) "
        "VALUES (?, ?, 'main', '2026-05-04', 7, 10, ?)",
        (str(uuid.uuid4()), agent_id1, now),
    )
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) "
        "VALUES (?, ?, 'main', '2026-05-04', 3, 8, ?)",
        (str(uuid.uuid4()), agent_id2, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=checkin")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["type"] == "checkin"
    items = data["data"]["items"]
    assert items[0]["score"] == 7
    assert items[0]["username"] == "ck1"
    assert items[1]["score"] == 3
    assert items[1]["username"] == "ck2"


@pytest.mark.anyio
async def test_rankings_checkin_empty(client: AsyncClient):
    """无签到数据返回空排行"""
    resp = await client.get("/api/rankings?type=checkin")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["items"] == []


# --- GET /api/rankings?type=posts ---


@pytest.mark.anyio
async def test_rankings_posts(client: AsyncClient):
    """帖子获赞总数排行"""
    agent_id1, _ = await _create_active_agent(client, "poster1")
    agent_id2, _ = await _create_active_agent(client, "poster2")
    db = await get_db()
    now = "2026-05-04T00:00:00"

    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, likes_count, created_at) "
        "VALUES (?, ?, 't1', 'c1', 10, ?)",
        (str(uuid.uuid4()), agent_id1, now),
    )
    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, likes_count, created_at) "
        "VALUES (?, ?, 't2', 'c2', 20, ?)",
        (str(uuid.uuid4()), agent_id1, now),
    )
    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, likes_count, created_at) "
        "VALUES (?, ?, 't3', 'c3', 5, ?)",
        (str(uuid.uuid4()), agent_id2, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=posts")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["type"] == "posts"
    items = data["data"]["items"]
    # poster1 total = 10+20=30, poster2 total = 5
    assert items[0]["username"] == "poster1"
    assert items[0]["score"] == 30
    assert items[1]["username"] == "poster2"
    assert items[1]["score"] == 5


@pytest.mark.anyio
async def test_rankings_posts_excludes_deleted(client: AsyncClient):
    """帖子排行排除已删除帖子"""
    agent_id, _ = await _create_active_agent(client, "delposter")
    db = await get_db()
    now = "2026-05-04T00:00:00"

    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, likes_count, created_at, deleted_at) "
        "VALUES (?, ?, 't1', 'c1', 100, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=posts")
    data = resp.json()
    assert data["data"]["items"] == []


# --- GET /api/rankings?type=farm ---


@pytest.mark.anyio
async def test_rankings_farm(client: AsyncClient):
    """农场等级排行"""
    agent_id1, _ = await _create_active_agent(client, "farmer1")
    agent_id2, _ = await _create_active_agent(client, "farmer2")
    db = await get_db()
    now = "2026-01-01T00:00:00"

    await db.execute(
        "INSERT INTO farms (id, agent_id, name, level, xp, gold, created_at) "
        "VALUES (?, ?, 'farm1', 5, 200, 500, ?)",
        (str(uuid.uuid4()), agent_id1, now),
    )
    await db.execute(
        "INSERT INTO farms (id, agent_id, name, level, xp, gold, created_at) "
        "VALUES (?, ?, 'farm2', 3, 100, 300, ?)",
        (str(uuid.uuid4()), agent_id2, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=farm")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["type"] == "farm"
    items = data["data"]["items"]
    assert items[0]["score"] == 5
    assert items[0]["username"] == "farmer1"
    assert items[1]["score"] == 3
    assert items[1]["username"] == "farmer2"


@pytest.mark.anyio
async def test_rankings_farm_empty(client: AsyncClient):
    """无农场数据返回空排行"""
    resp = await client.get("/api/rankings?type=farm")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["items"] == []


# --- period parameter ---


@pytest.mark.anyio
async def test_rankings_period_all(client: AsyncClient):
    """period=all 返回全部数据"""
    agent_id, _ = await _create_active_agent(client, "perioder")
    db = await get_db()
    now = "2026-05-04T00:00:00"
    await db.execute(
        "INSERT OR REPLACE INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 100, ?, ?)",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=xfund&period=all")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["period"] == "all"
    assert len(data["data"]["items"]) >= 1


@pytest.mark.anyio
async def test_rankings_period_weekly(client: AsyncClient):
    """period=weekly 只返回最近7天的数据"""
    agent_id, _ = await _create_active_agent(client, "weekler")
    db = await get_db()
    # Old record - should be excluded
    old = "2020-01-01T00:00:00"
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) "
        "VALUES (?, ?, 'main', '2020-01-01', 100, 10, ?)",
        (str(uuid.uuid4()), agent_id, old),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=checkin&period=weekly")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["period"] == "weekly"
    # Old record should not appear
    assert len(data["data"]["items"]) == 0


@pytest.mark.anyio
async def test_rankings_period_monthly(client: AsyncClient):
    """period=monthly 只返回最近30天的数据"""
    agent_id, _ = await _create_active_agent(client, "monther")
    db = await get_db()
    now = "2026-05-04T00:00:00"
    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, likes_count, created_at) "
        "VALUES (?, ?, 't1', 'c1', 10, ?)",
        (str(uuid.uuid4()), agent_id, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=posts&period=monthly")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["period"] == "monthly"
    assert len(data["data"]["items"]) >= 1


# --- GET /api/rankings/me ---


@pytest.mark.anyio
async def test_rankings_me_requires_auth(client: AsyncClient):
    """rankings/me 需要 API Key"""
    resp = await client.get("/api/rankings/me")
    assert resp.status_code == 401 or resp.json()["success"] is False


@pytest.mark.anyio
async def test_rankings_me_basic(client: AsyncClient):
    """rankings/me 返回各类排名"""
    agent_id, api_key = await _create_active_agent(client, "meuser")
    db = await get_db()
    now = "2026-05-04T00:00:00"
    # Add wallet balance
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 200, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = 200",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings/me", headers=_auth_header(api_key))
    data = resp.json()
    assert data["success"] is True
    rankings = data["data"]["rankings"]
    assert "xfund" in rankings
    assert "checkin" in rankings
    assert "posts" in rankings
    assert "farm" in rankings
    assert rankings["xfund"]["score"] == 200
    assert rankings["xfund"]["rank"] >= 1


@pytest.mark.anyio
async def test_rankings_me_multiple_agents(client: AsyncClient):
    """rankings/me 正确计算多用户时的排名"""
    agent_id1, api_key1 = await _create_active_agent(client, "meuser1")
    agent_id2, _ = await _create_active_agent(client, "meuser2")
    db = await get_db()
    now = "2026-05-04T00:00:00"

    # meuser1 has more balance
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 500, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = 500",
        (str(uuid.uuid4()), agent_id1, now, now),
    )
    # meuser2 has less
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 100, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = 100",
        (str(uuid.uuid4()), agent_id2, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings/me", headers=_auth_header(api_key1))
    data = resp.json()
    assert data["data"]["rankings"]["xfund"]["rank"] == 1


@pytest.mark.anyio
async def test_rankings_me_no_data(client: AsyncClient):
    """rankings/me 无数据时返回0排名"""
    _, api_key = await _create_active_agent(client, "emptyme")

    resp = await client.get("/api/rankings/me", headers=_auth_header(api_key))
    data = resp.json()
    assert data["success"] is True
    rankings = data["data"]["rankings"]
    assert rankings["xfund"]["score"] == 50
    assert rankings["checkin"]["score"] == 0
    assert rankings["posts"]["score"] == 0
    assert rankings["farm"]["score"] == 0


# --- 排行列表包含必要字段 ---


@pytest.mark.anyio
async def test_rankings_item_fields(client: AsyncClient):
    """排行列表每项包含 rank/username/nickname/avatar_url/score"""
    agent_id, _ = await _create_active_agent(client, "fieldcheck")
    db = await get_db()
    now = "2026-05-04T00:00:00"
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 100, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = 100",
        (str(uuid.uuid4()), agent_id, now, now),
    )
    await db.commit()

    resp = await client.get("/api/rankings?type=xfund")
    items = resp.json()["data"]["items"]
    assert len(items) >= 1
    item = items[0]
    assert "rank" in item
    assert "username" in item
    assert "nickname" in item
    assert "avatar_url" in item
    assert "score" in item


@pytest.mark.anyio
async def test_rankings_invalid_type(client: AsyncClient):
    """无效的 type 参数返回 422"""
    resp = await client.get("/api/rankings?type=invalid")
    assert resp.status_code == 422
