"""NeverLand 种植系统测试"""
import uuid
from datetime import datetime, timedelta, timezone

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


async def _register_farm(client: AsyncClient, api_key: str, name: str = "测试农场") -> str:
    """注册农场并返回 farm_id"""
    resp = await client.post(
        "/api/neverland/farm/register",
        json={"name": name},
        headers={"agent-auth-api-key": api_key},
    )
    return resp.json()["data"]["id"]


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


# --- 作物列表测试 ---

@pytest.mark.anyio
async def test_get_crops():
    """测试获取可种植的作物列表"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/neverland/farm/crops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        crops = data["data"]["crops"]
        assert len(crops) == 5

        crop_types = {c["crop_type"] for c in crops}
        assert crop_types == {"carrot", "wheat", "tomato", "apple", "rose"}

        # 验证每种作物包含必要字段
        for c in crops:
            assert "name" in c
            assert "seed_price" in c
            assert "growth_days" in c
            assert "harvest_value" in c
            assert c["seed_price"] > 0
            assert c["growth_days"] > 0
            assert c["harvest_value"] > 0


@pytest.mark.anyio
async def test_get_crops_no_auth_required():
    """测试作物列表无需认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/neverland/farm/crops")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# --- 种植测试 ---

@pytest.mark.anyio
async def test_plant_crop():
    """测试种植作物"""
    api_key = await _create_active_agent("planter1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        farm_id = await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["crop_type"] == "carrot"
        assert data["data"]["seed_price"] == 5
        assert data["data"]["growth_days"] == 1
        assert data["data"]["status"] == "planted"

        # 验证金币扣除
        farm_resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        assert farm_resp.json()["data"]["gold"] == 95


@pytest.mark.anyio
async def test_plant_crop_insufficient_gold():
    """测试金币不足时种植"""
    api_key = await _create_active_agent("poorfarmer")
    db = await get_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        farm_id = await _register_farm(client, api_key)

        # 把金币改为 3（不够种胡萝卜的 5）
        await db.execute("UPDATE farms SET gold = 3 WHERE id = ?", (farm_id,))
        await db.commit()

        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "insufficient_gold" in data["error"]


@pytest.mark.anyio
async def test_plant_crop_invalid_type():
    """测试种植不存在的作物"""
    api_key = await _create_active_agent("planter2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "unicorn"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "invalid_crop" in data["error"]


@pytest.mark.anyio
async def test_plant_crop_already_planted():
    """测试在已种植的农田上再次种植"""
    api_key = await _create_active_agent("planter3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        # 先种植
        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.json()["success"] is True

        # 再种一次
        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "wheat"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "plot_not_empty" in data["error"]


@pytest.mark.anyio
async def test_plant_crop_invalid_plot_index():
    """测试种植到不存在的农田编号"""
    api_key = await _create_active_agent("planter4")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/plots/99/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "invalid_plot" in data["error"]


@pytest.mark.anyio
async def test_plant_crop_requires_auth():
    """测试种植需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
        )
        assert resp.status_code == 401 or (resp.status_code == 200 and resp.json()["success"] is False)


@pytest.mark.anyio
async def test_plant_crop_no_farm():
    """测试未注册农场时种植"""
    api_key = await _create_active_agent("nofarm")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_found" in data["error"]


@pytest.mark.anyio
async def test_plant_all_crop_types():
    """测试种植所有类型的作物"""
    api_key = await _create_active_agent("greedyfarmer")
    db = await get_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        farm_id = await _register_farm(client, api_key)

        # 修改金币为足够多
        await db.execute("UPDATE farms SET gold = 1000 WHERE id = ?", (farm_id,))
        await db.commit()

        crops_to_plant = ["carrot", "wheat", "tomato", "apple", "rose"]
        for i, crop_type in enumerate(crops_to_plant):
            resp = await client.post(
                f"/api/neverland/farm/plots/{i}/plant",
                json={"crop_type": crop_type},
                headers={"agent-auth-api-key": api_key},
            )
            assert resp.json()["success"] is True, f"种植 {crop_type} 失败: {resp.json()}"


# --- 浇水测试 ---

@pytest.mark.anyio
async def test_water_crop():
    """测试浇水"""
    api_key = await _create_active_agent("waterer1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        # 先种植
        await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )

        # 浇水
        resp = await client.post(
            "/api/neverland/farm/plots/0/water",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["watered_at"] is not None


@pytest.mark.anyio
async def test_water_empty_plot():
    """测试对空农田浇水"""
    api_key = await _create_active_agent("waterer2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/plots/0/water",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_planted" in data["error"]


@pytest.mark.anyio
async def test_water_requires_auth():
    """测试浇水需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/neverland/farm/plots/0/water")
        assert resp.status_code == 401 or (resp.status_code == 200 and resp.json()["success"] is False)


# --- 收获测试 ---

@pytest.mark.anyio
async def test_harvest_mature_crop():
    """测试收获成熟作物"""
    api_key = await _create_active_agent("harvester1")
    db = await get_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        farm_id = await _register_farm(client, api_key)

        # 先种植
        await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )

        # 手动将 planted_at 设为 2 天前（carrot 成熟需 1 天）
        past_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "UPDATE farm_plots SET planted_at = ? WHERE farm_id = ? AND plot_index = 0",
            (past_time, farm_id),
        )
        await db.commit()

        # 收获
        resp = await client.post(
            "/api/neverland/farm/plots/0/harvest",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["crop_type"] == "carrot"
        assert data["data"]["harvest_value"] == 10
        assert data["data"]["xp_gained"] == 5

        # 验证金币增加（初始100-5种子+10收获=105）
        farm_resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        assert farm_resp.json()["data"]["gold"] == 105


@pytest.mark.anyio
async def test_harvest_not_mature():
    """测试收获未成熟的作物"""
    api_key = await _create_active_agent("harvester2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        # 种植苹果（需5天成熟）
        await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "apple"},
            headers={"agent-auth-api-key": api_key},
        )

        # 立即尝试收获
        resp = await client.post(
            "/api/neverland/farm/plots/0/harvest",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_mature" in data["error"]


@pytest.mark.anyio
async def test_harvest_empty_plot():
    """测试收获空农田"""
    api_key = await _create_active_agent("harvester3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/plots/0/harvest",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_planted" in data["error"]


@pytest.mark.anyio
async def test_harvest_resets_plot():
    """测试收获后农田恢复为空"""
    api_key = await _create_active_agent("harvester4")
    db = await get_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        farm_id = await _register_farm(client, api_key)

        # 种植
        await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "wheat"},
            headers={"agent-auth-api-key": api_key},
        )

        # 设为已成熟
        past_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        await db.execute(
            "UPDATE farm_plots SET planted_at = ? WHERE farm_id = ? AND plot_index = 0",
            (past_time, farm_id),
        )
        await db.commit()

        # 收获
        resp = await client.post(
            "/api/neverland/farm/plots/0/harvest",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.json()["success"] is True

        # 验证农田恢复为空
        cursor = await db.execute(
            "SELECT status, crop_type FROM farm_plots WHERE farm_id = ? AND plot_index = 0",
            (farm_id,),
        )
        plot = await cursor.fetchone()
        assert plot["status"] == "empty"
        assert plot["crop_type"] == ""

        # 可以再次种植
        resp = await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_harvest_requires_auth():
    """测试收获需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/neverland/farm/plots/0/harvest")
        assert resp.status_code == 401 or (resp.status_code == 200 and resp.json()["success"] is False)


@pytest.mark.anyio
async def test_harvest_invalid_plot():
    """测试收获不存在的农田"""
    api_key = await _create_active_agent("harvester5")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/plots/99/harvest",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "invalid_plot" in data["error"]


@pytest.mark.anyio
async def test_harvest_increases_xp():
    """测试收获增加经验值"""
    api_key = await _create_active_agent("xpplayer")
    db = await get_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        farm_id = await _register_farm(client, api_key)

        # 种植并设为成熟
        await client.post(
            "/api/neverland/farm/plots/0/plant",
            json={"crop_type": "carrot"},
            headers={"agent-auth-api-key": api_key},
        )

        past_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "UPDATE farm_plots SET planted_at = ? WHERE farm_id = ? AND plot_index = 0",
            (past_time, farm_id),
        )
        await db.commit()

        # 收获
        await client.post(
            "/api/neverland/farm/plots/0/harvest",
            headers={"agent-auth-api-key": api_key},
        )

        # 验证 XP
        cursor = await db.execute("SELECT xp FROM farms WHERE id = ?", (farm_id,))
        farm = await cursor.fetchone()
        assert farm["xp"] == 5
