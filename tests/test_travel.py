"""TravelMind-随机漫步 测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


@pytest.fixture(autouse=True)
async def _clean_travel_tables():
    """每个测试前清空 visits 表"""
    db = await get_db()
    await db.execute("DELETE FROM visits")
    await db.execute("DELETE FROM agents")
    await db.execute("DELETE FROM wallets")
    await db.commit()
    yield


async def _create_active_agent(username: str = "traveler") -> tuple[str, str]:
    """创建激活 agent 并返回 (agent_id, api_key)"""
    db = await get_db()
    import uuid
    agent_id = str(uuid.uuid4())
    api_key = "agent-world-" + "a" * 48
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO agents (agent_id, username, nickname, api_key, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (agent_id, username, username, api_key, now),
    )
    await db.commit()
    return agent_id, api_key


async def _seed_landmarks():
    """确保景点数据已初始化"""
    from src.services.landmark_seeds import seed_landmarks
    await seed_landmarks()


@pytest.mark.anyio
async def test_list_landmarks_no_auth():
    """无需认证可查看景点列表"""
    await _seed_landmarks()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/travel/landmarks")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 20
    # 无认证时 visited 都为 False
    assert data["data"]["landmarks"][0]["visited"] is False


@pytest.mark.anyio
async def test_list_landmarks_with_auth():
    """认证后景点列表显示打卡状态"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("lm_auth")
    db = await get_db()
    # 获取一个景点 ID
    cursor = await db.execute("SELECT id FROM landmarks LIMIT 1")
    lm = await cursor.fetchone()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 打卡一个
        resp = await ac.post(
            f"/api/travel/landmarks/{lm['id']}/visit",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.json()["success"] is True

        # 查看列表
        resp = await ac.get(
            "/api/travel/landmarks",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is True
    visited = [lm for lm in data["data"]["landmarks"] if lm["visited"]]
    assert len(visited) == 1
    assert visited[0]["id"] == lm["id"]


@pytest.mark.anyio
async def test_discover_landmark():
    """随机推荐未打卡景点"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("discover1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/travel/discover",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert "landmark" in data["data"]
    assert "name" in data["data"]["landmark"]
    assert "country" in data["data"]["landmark"]


@pytest.mark.anyio
async def test_discover_requires_auth():
    """发现景点需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/travel/discover")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_discover_all_visited():
    """所有景点都已打卡时返回提示"""
    await _seed_landmarks()
    agent_id, api_key = await _create_active_agent("allvisit")
    db = await get_db()

    # 打卡所有景点
    cursor = await db.execute("SELECT id FROM landmarks")
    landmarks = await cursor.fetchall()
    import uuid, datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for lm in landmarks:
        await db.execute(
            "INSERT INTO visits (id, agent_id, landmark_id, visited_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, lm["id"], now),
        )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/travel/discover",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "all_visited"


@pytest.mark.anyio
async def test_visit_landmark():
    """打卡景点成功 +2 虾米"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("visit1")
    db = await get_db()
    cursor = await db.execute("SELECT id, name FROM landmarks LIMIT 1")
    lm = await cursor.fetchone()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/travel/landmarks/{lm['id']}/visit",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward"] == 2
    assert data["data"]["landmark_name"] == lm["name"]

    # 验证虾米余额
    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = (SELECT agent_id FROM agents WHERE username = 'visit1')"
    )
    wallet = await cursor.fetchone()
    assert wallet["balance"] == 2


@pytest.mark.anyio
async def test_visit_duplicate():
    """重复打卡同一景点报错"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("visitdup")
    db = await get_db()
    cursor = await db.execute("SELECT id FROM landmarks LIMIT 1")
    lm = await cursor.fetchone()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 第一次打卡
        resp = await ac.post(
            f"/api/travel/landmarks/{lm['id']}/visit",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.json()["success"] is True

        # 第二次打卡
        resp = await ac.post(
            f"/api/travel/landmarks/{lm['id']}/visit",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "duplicate"


@pytest.mark.anyio
async def test_visit_not_found():
    """打卡不存在的景点"""
    _, api_key = await _create_active_agent("visitnf")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/travel/landmarks/nonexistent-id/visit",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_visit_requires_auth():
    """打卡需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/travel/landmarks/some-id/visit")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_my_visits():
    """我的打卡记录分页"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("myvisit")
    db = await get_db()

    # 获取两个景点
    cursor = await db.execute("SELECT id FROM landmarks LIMIT 2")
    landmarks = await cursor.fetchall()

    import uuid, datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor = await db.execute("SELECT agent_id FROM agents WHERE username = 'myvisit'")
    agent_id = (await cursor.fetchone())["agent_id"]

    for lm in landmarks:
        await db.execute(
            "INSERT INTO visits (id, agent_id, landmark_id, visited_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, lm["id"], now),
        )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/travel/visits",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 2
    assert len(data["data"]["visits"]) == 2
    assert "landmark" in data["data"]["visits"][0]


@pytest.mark.anyio
async def test_list_visits_pagination():
    """打卡记录分页"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("visitpag")
    db = await get_db()

    import uuid, datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor = await db.execute("SELECT agent_id FROM agents WHERE username = 'visitpag'")
    agent_id = (await cursor.fetchone())["agent_id"]

    # 打卡3个景点
    cursor = await db.execute("SELECT id FROM landmarks LIMIT 3")
    landmarks = await cursor.fetchall()
    for lm in landmarks:
        await db.execute(
            "INSERT INTO visits (id, agent_id, landmark_id, visited_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, lm["id"], now),
        )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/travel/visits?page=1&limit=2",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 3
    assert len(data["data"]["visits"]) == 2
    assert data["data"]["page"] == 1


@pytest.mark.anyio
async def test_list_visits_requires_auth():
    """打卡记录需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/travel/visits")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_landmark_data_completeness():
    """景点数据包含完整信息"""
    await _seed_landmarks()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/travel/landmarks")
    data = resp.json()
    assert data["success"] is True
    lm = data["data"]["landmarks"][0]
    assert "id" in lm
    assert "name" in lm
    assert "description" in lm
    assert "country" in lm
    assert "tags" in lm
    assert "latitude" in lm
    assert "longitude" in lm


@pytest.mark.anyio
async def test_discover_excludes_visited():
    """发现景点排除已打卡的"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("discexc")
    db = await get_db()

    # 打卡所有景点 except one
    import uuid, datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor = await db.execute("SELECT agent_id FROM agents WHERE username = 'discexc'")
    agent_id = (await cursor.fetchone())["agent_id"]

    cursor = await db.execute("SELECT id FROM landmarks")
    all_lms = await cursor.fetchall()
    # 打卡前19个，保留最后一个
    for lm in all_lms[:-1]:
        await db.execute(
            "INSERT INTO visits (id, agent_id, landmark_id, visited_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, lm["id"], now),
        )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/travel/discover",
            headers={"agent-auth-api-key": api_key},
        )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["landmark"]["id"] == all_lms[-1]["id"]


@pytest.mark.anyio
async def test_visit_multiple_accumulates_reward():
    """打卡多个景点虾米累加"""
    await _seed_landmarks()
    _, api_key = await _create_active_agent("multvisit")
    db = await get_db()

    cursor = await db.execute("SELECT id FROM landmarks LIMIT 3")
    landmarks = await cursor.fetchall()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for lm in landmarks:
            resp = await ac.post(
                f"/api/travel/landmarks/{lm['id']}/visit",
                headers={"agent-auth-api-key": api_key},
            )
            assert resp.json()["success"] is True

    # 验证虾米 = 3 * 2 = 6
    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = (SELECT agent_id FROM agents WHERE username = 'multvisit')"
    )
    wallet = await cursor.fetchone()
    assert wallet["balance"] == 6
