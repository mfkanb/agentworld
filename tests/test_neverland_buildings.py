"""NeverLand 建筑与动物系统测试"""
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


async def _register_farm(client: AsyncClient, api_key: str, name: str = "测试农场") -> dict:
    """注册农场并返回响应 data"""
    resp = await client.post(
        "/api/neverland/farm/register",
        json={"name": name},
        headers={"agent-auth-api-key": api_key},
    )
    return resp.json()["data"]


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
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


# --- 建筑测试 ---

@pytest.mark.anyio
async def test_build_chicken_coop():
    """测试建造鸡舍"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("builder1")
        farm = await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["building_type"] == "chicken_coop"
        assert data["data"]["building_name"] == "鸡舍"
        assert data["data"]["price"] == 100
        assert data["data"]["level"] == 1

        # 验证金币扣除
        resp2 = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp2.json()["data"]["gold"] == 0  # 100 - 100


@pytest.mark.anyio
async def test_build_all_building_types():
    """测试建造所有类型建筑"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("builder2")
        # 先手动给农场加金币以测试
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 1000 WHERE id = ?", (farm["id"],))
        await db.commit()

        for btype in ["chicken_coop", "barn", "silo", "greenhouse"]:
            resp = await client.post(
                "/api/neverland/farm/buildings",
                json={"building_type": btype},
                headers={"agent-auth-api-key": api_key},
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_build_invalid_building():
    """测试建造无效建筑类型"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("builder3")
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "castle"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "invalid_building" in data["error"]


@pytest.mark.anyio
async def test_build_insufficient_gold():
    """测试金币不足建造"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("builder4")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        # 设金币为 50
        await db.execute("UPDATE farms SET gold = 50 WHERE id = ?", (farm["id"],))
        await db.commit()

        resp = await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},  # 需要100金
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "insufficient_gold" in data["error"]


@pytest.mark.anyio
async def test_build_no_farm():
    """测试未注册农场时建造"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("builder5")

        resp = await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_found" in data["error"]


# --- 建筑列表测试 ---

@pytest.mark.anyio
async def test_get_buildings():
    """测试获取建筑列表"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("builder6")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 1000 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 建造两个建筑
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "barn"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.get(
            "/api/neverland/farm/buildings",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["buildings"]) == 2


# --- 动物测试 ---

@pytest.mark.anyio
async def test_buy_chicken():
    """测试购买鸡"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("farmer1")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 200 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 先建鸡舍
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["animal_type"] == "chicken"
        assert data["data"]["animal_name"] == "鸡"
        assert data["data"]["price"] == 20
        assert data["data"]["product_name"] == "鸡蛋"
        assert data["data"]["product_value"] == 3

        # 验证金币扣除 200 - 100(鸡舍) - 20(鸡) = 80
        resp2 = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp2.json()["data"]["gold"] == 80


@pytest.mark.anyio
async def test_buy_animal_without_building():
    """测试没有对应建筑时购买动物"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("farmer2")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 200 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 没有建鸡舍就买鸡
        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "building_required" in data["error"]


@pytest.mark.anyio
async def test_buy_all_animal_types():
    """测试购买所有类型动物"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("farmer3")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 1000 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 建造鸡舍和畜棚
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "barn"},
            headers={"agent-auth-api-key": api_key},
        )

        for atype in ["chicken", "duck", "rabbit", "sheep"]:
            resp = await client.post(
                "/api/neverland/farm/animals",
                json={"animal_type": atype},
                headers={"agent-auth-api-key": api_key},
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_buy_invalid_animal():
    """测试购买无效动物类型"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("farmer4")
        await _register_farm(client, api_key)

        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "dragon"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "invalid_animal" in data["error"]


@pytest.mark.anyio
async def test_buy_animal_insufficient_gold():
    """测试金币不足购买动物"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("farmer5")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        # 先建鸡舍（100金），然后金币只剩0
        await db.execute("UPDATE farms SET gold = 100 WHERE id = ?", (farm["id"],))
        await db.commit()

        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "insufficient_gold" in data["error"]


# --- 收集产品测试 ---

@pytest.mark.anyio
async def test_collect_product():
    """测试首次收集产品"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("collector1")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 200 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 建鸡舍 + 买鸡
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )
        animal_id = resp.json()["data"]["id"]

        # 收集鸡蛋
        resp = await client.post(
            f"/api/neverland/farm/animals/{animal_id}/collect",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["product_name"] == "鸡蛋"
        assert data["data"]["product_value"] == 3


@pytest.mark.anyio
async def test_collect_product_gold_increase():
    """测试收集产品后金币增加"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("collector2")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 300 WHERE id = ?", (farm["id"],))
        await db.commit()

        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "barn"},
            headers={"agent-auth-api-key": api_key},
        )
        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "sheep"},
            headers={"agent-auth-api-key": api_key},
        )
        animal_id = resp.json()["data"]["id"]

        # 收集前金币: 300 - 200(barn) - 50(sheep) = 50
        gold_before = (await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )).json()["data"]["gold"]

        # 收集羊毛（价值8）
        await client.post(
            f"/api/neverland/farm/animals/{animal_id}/collect",
            headers={"agent-auth-api-key": api_key},
        )

        gold_after = (await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )).json()["data"]["gold"]

        assert gold_after == gold_before + 8


@pytest.mark.anyio
async def test_collect_cooldown():
    """测试24小时冷却"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("collector3")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 200 WHERE id = ?", (farm["id"],))
        await db.commit()

        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )
        animal_id = resp.json()["data"]["id"]

        # 第一次收集
        await client.post(
            f"/api/neverland/farm/animals/{animal_id}/collect",
            headers={"agent-auth-api-key": api_key},
        )

        # 立即第二次收集应失败（冷却中）
        resp = await client.post(
            f"/api/neverland/farm/animals/{animal_id}/collect",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "cooldown" in data["error"]


@pytest.mark.anyio
async def test_collect_after_cooldown():
    """测试冷却结束后可以再次收集"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("collector4")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 200 WHERE id = ?", (farm["id"],))
        await db.commit()

        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )
        animal_id = resp.json()["data"]["id"]

        # 手动设置 last_collected_at 为 25 小时前
        past_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        await db.execute(
            "UPDATE farm_animals SET last_collected_at = ? WHERE id = ?",
            (past_time, animal_id),
        )
        await db.commit()

        # 冷却结束后应该能收集
        resp = await client.post(
            f"/api/neverland/farm/animals/{animal_id}/collect",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["product_value"] == 3


@pytest.mark.anyio
async def test_collect_not_own_animal():
    """测试收集别人的动物"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key1 = await _create_active_agent("collector5")
        api_key2 = await _create_active_agent("collector6")
        db = await get_db()

        # 用户1建鸡舍买鸡
        farm1 = await _register_farm(client, api_key1, "农场1")
        await db.execute("UPDATE farms SET gold = 200 WHERE id = ?", (farm1["id"],))
        await db.commit()
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key1},
        )
        resp = await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key1},
        )
        animal_id = resp.json()["data"]["id"]

        # 用户2注册农场
        await _register_farm(client, api_key2, "农场2")

        # 用户2尝试收集用户1的鸡
        resp = await client.post(
            f"/api/neverland/farm/animals/{animal_id}/collect",
            headers={"agent-auth-api-key": api_key2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "forbidden" in data["error"]


@pytest.mark.anyio
async def test_collect_nonexistent_animal():
    """测试收集不存在的动物"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("collector7")
        await _register_farm(client, api_key)

        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/neverland/farm/animals/{fake_id}/collect",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not_found" in data["error"]


@pytest.mark.anyio
async def test_collect_all_product_values():
    """测试所有动物产品价值"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("collector8")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 1000 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 建鸡舍和畜棚
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "barn"},
            headers={"agent-auth-api-key": api_key},
        )

        expected = {
            "chicken": ("鸡蛋", 3),
            "duck": ("鸭蛋", 4),
            "rabbit": ("兔脚", 5),
            "sheep": ("羊毛", 8),
        }

        for atype, (pname, pvalue) in expected.items():
            resp = await client.post(
                "/api/neverland/farm/animals",
                json={"animal_type": atype},
                headers={"agent-auth-api-key": api_key},
            )
            animal_id = resp.json()["data"]["id"]

            resp = await client.post(
                f"/api/neverland/farm/animals/{animal_id}/collect",
                headers={"agent-auth-api-key": api_key},
            )
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["product_name"] == pname
            assert data["data"]["product_value"] == pvalue


@pytest.mark.anyio
async def test_farm_overview_shows_buildings_and_animals():
    """测试农场概况包含建筑和动物"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        api_key = await _create_active_agent("overview1")
        db = await get_db()
        farm = await _register_farm(client, api_key)
        await db.execute("UPDATE farms SET gold = 500 WHERE id = ?", (farm["id"],))
        await db.commit()

        # 建鸡舍 + 买鸡
        await client.post(
            "/api/neverland/farm/buildings",
            json={"building_type": "chicken_coop"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            "/api/neverland/farm/animals",
            json={"animal_type": "chicken"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.get(
            "/api/neverland/farm",
            headers={"agent-auth-api-key": api_key},
        )
        data = resp.json()["data"]
        assert len(data["buildings"]) == 1
        assert data["buildings"][0]["building_type"] == "chicken_coop"
        assert len(data["animals"]) == 1
        assert data["animals"][0]["animal_type"] == "chicken"
