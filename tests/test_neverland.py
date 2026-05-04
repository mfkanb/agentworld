"""NeverLand 农场养成测试"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


async def _create_active_agent(username: str = "testuser") -> str:
    """创建已激活 agent 并返回 API Key"""
    db = await get_db()
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO agents (agent_id, username, nickname, bio, avatar_url, api_key, is_active, verification_code, challenge_answer, challenge_expires_at, attempt_count, created_at)
           VALUES (?, ?, ?, '', '', ?, 1, '', '', '', 0, ?)""",
        (agent_id, username, username, f"agent-world-testkey-{username}", now),
    )
    await db.commit()
    return f"agent-world-testkey-{username}"


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空 neverland 相关表"""
    db = await get_db()
    await db.execute("DELETE FROM farm_gifts")
    await db.execute("DELETE FROM farm_achievements")
    await db.execute("DELETE FROM farm_animals")
    await db.execute("DELETE FROM farm_buildings")
    await db.execute("DELETE FROM farm_plots")
    await db.execute("DELETE FROM farms")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_register_farm():
    """测试注册农场"""
    api_key = await _create_active_agent("farmer1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "阳光农场", "description": "一个美丽的农场"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["name"] == "阳光农场"
        assert data["data"]["description"] == "一个美丽的农场"
        assert data["data"]["level"] == 1
        assert data["data"]["xp"] == 0
        assert data["data"]["gold"] == 100
        assert data["data"]["reputation"] == 0
        assert data["data"]["plots_count"] == 6


@pytest.mark.anyio
async def test_register_farm_creates_plots():
    """测试注册农场时自动创建6块农田"""
    api_key = await _create_active_agent("farmer2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "测试农场"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        farm_id = resp.json()["data"]["id"]

        # 验证数据库中创建了6块农田
        db = await get_db()
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM farm_plots WHERE farm_id = ?",
            (farm_id,),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 6

        # 验证所有农田都是空状态
        cursor = await db.execute(
            "SELECT DISTINCT status FROM farm_plots WHERE farm_id = ?",
            (farm_id,),
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "empty"


@pytest.mark.anyio
async def test_register_farm_duplicate():
    """测试重复注册农场"""
    api_key = await _create_active_agent("farmer3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 第一次注册
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "农场1"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200

        # 第二次注册
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "农场2"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "duplicate" in data["error"]


@pytest.mark.anyio
async def test_register_farm_requires_auth():
    """测试注册农场需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "农场"},
        )
        assert resp.status_code == 401 or (resp.status_code == 200 and resp.json()["success"] is False)


@pytest.mark.anyio
async def test_register_farm_name_required():
    """测试农场名称必填"""
    api_key = await _create_active_agent("farmer4")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"description": "没有名字"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_farm_description_optional():
    """测试农场描述可选"""
    api_key = await _create_active_agent("farmer5")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "简约农场"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["description"] == ""


@pytest.mark.anyio
async def test_get_farm():
    """测试查看农场概况"""
    api_key = await _create_active_agent("farmer6")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 先注册
        await client.post(
            "/api/neverland/farm/register",
            json={"name": "我的农场", "description": "很好"},
            headers={"agent-auth-api-key": api_key},
        )

        # 查看概况
        resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["name"] == "我的农场"
        assert data["data"]["level"] == 1
        assert data["data"]["gold"] == 100
        assert data["data"]["reputation"] == 0
        assert data["data"]["plots_count"] == 6
        assert len(data["data"]["plots"]) == 6
        assert data["data"]["buildings"] == []
        assert data["data"]["animals"] == []


@pytest.mark.anyio
async def test_get_farm_not_registered():
    """测试未注册农场时查看概况"""
    api_key = await _create_active_agent("farmer7")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_found" in data["error"]


@pytest.mark.anyio
async def test_get_farm_requires_auth():
    """测试查看农场需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/neverland/farm")
        assert resp.status_code == 401 or (resp.status_code == 200 and resp.json()["success"] is False)


@pytest.mark.anyio
async def test_get_farm_plots_detail():
    """测试农场概况包含正确的农田详情"""
    api_key = await _create_active_agent("farmer8")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/neverland/farm/register",
            json={"name": "农田测试"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        data = resp.json()
        plots = data["data"]["plots"]

        # 6 块农田，索引 0-5，全部为空
        assert len(plots) == 6
        indices = [p["plot_index"] for p in plots]
        assert sorted(indices) == [0, 1, 2, 3, 4, 5]
        for plot in plots:
            assert plot["crop_type"] == ""
            assert plot["status"] == "empty"


@pytest.mark.anyio
async def test_register_farm_with_buildings_and_animals():
    """测试注册农场后添加建筑和动物的概况"""
    api_key = await _create_active_agent("farmer9")
    db = await get_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "综合农场"},
            headers={"agent-auth-api-key": api_key},
        )
        farm_id = resp.json()["data"]["id"]
        now = datetime.now(timezone.utc).isoformat()

        # 手动插入建筑和动物来测试概况查询
        await db.execute(
            "INSERT INTO farm_buildings (id, farm_id, building_type, level, built_at) VALUES (?, ?, 'chicken_coop', 1, ?)",
            (str(uuid.uuid4()), farm_id, now),
        )
        await db.execute(
            "INSERT INTO farm_animals (id, farm_id, animal_type, name, created_at) VALUES (?, ?, 'chicken', '小黄', ?)",
            (str(uuid.uuid4()), farm_id, now),
        )
        await db.commit()

        resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["buildings"]) == 1
        assert data["data"]["buildings"][0]["building_type"] == "chicken_coop"
        assert len(data["data"]["animals"]) == 1
        assert data["data"]["animals"][0]["animal_type"] == "chicken"
        assert data["data"]["animals"][0]["name"] == "小黄"


@pytest.mark.anyio
async def test_tables_created():
    """验证 NeverLand 相关表已创建"""
    db = await get_db()
    for table in ["farms", "farm_plots", "farm_buildings", "farm_animals", "farm_achievements", "farm_gifts"]:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        row = await cursor.fetchone()
        assert row is not None, f"表 {table} 未创建"


@pytest.mark.anyio
async def test_farm_name_max_length():
    """测试农场名称超长"""
    api_key = await _create_active_agent("farmer10")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/register",
            json={"name": "x" * 101},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_multiple_agents_separate_farms():
    """测试多个 Agent 各自拥有独立农场"""
    key1 = await _create_active_agent("farmer_a")
    key2 = await _create_active_agent("farmer_b")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.post(
            "/api/neverland/farm/register",
            json={"name": "农场A"},
            headers={"agent-auth-api-key": key1},
        )
        resp2 = await client.post(
            "/api/neverland/farm/register",
            json={"name": "农场B"},
            headers={"agent-auth-api-key": key2},
        )
        assert resp1.json()["success"] is True
        assert resp2.json()["success"] is True
        assert resp1.json()["data"]["id"] != resp2.json()["data"]["id"]
        assert resp1.json()["data"]["name"] == "农场A"
        assert resp2.json()["data"]["name"] == "农场B"
