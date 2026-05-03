"""US-020 酒馆-酒水系统测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db
from src.services.drink_seeds import seed_drinks


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
    """每个测试前清空相关表并初始化酒水"""
    db = await get_db()
    await db.execute("DELETE FROM drink_sessions")
    await db.execute("DELETE FROM drinks")
    await db.execute("DELETE FROM agents")
    await db.execute("DELETE FROM wallets")
    await db.commit()
    # 重新 seed 酒水
    await seed_drinks()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "bartestuser") -> tuple[str, str]:
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
    return verify_data["agent_id"], verify_data["api_key"]


def _auth_headers(api_key: str) -> dict:
    return {"agent-auth-api-key": api_key}


@pytest.mark.anyio
async def test_list_drinks(client):
    """GET /drinks 返回15款酒水"""
    resp = await client.get("/drinks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    items = body["data"]["items"]
    assert len(items) == 15
    drink = items[0]
    assert "id" in drink
    assert "name" in drink
    assert "code" in drink
    assert "description" in drink
    assert "taste_tags" in drink


@pytest.mark.anyio
async def test_list_drinks_no_auth(client):
    """GET /drinks 无需认证"""
    resp = await client.get("/drinks")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_random_drink(client):
    """POST /drink/random 随机点酒"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post("/drink/random", headers=_auth_headers(api_key))
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert "session_id" in data
    assert "drink" in data
    assert "name" in data["drink"]
    assert "code" in data["drink"]


@pytest.mark.anyio
async def test_random_drink_requires_auth(client):
    """POST /drink/random 需要认证"""
    resp = await client.post("/drink/random")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_order_specific_drink(client):
    """POST /drink 按 code 点指定酒"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post(
        "/drink",
        json={"drink_code": "quantum_martini"},
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["drink"]["code"] == "quantum_martini"
    assert data["drink"]["name"] == "量子马提尼"
    assert "session_id" in data


@pytest.mark.anyio
async def test_order_invalid_drink_code(client):
    """POST /drink 无效 code 返回 not_found"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post(
        "/drink",
        json={"drink_code": "nonexistent_drink"},
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "not_found" in body["error"]


@pytest.mark.anyio
async def test_consume_drink(client):
    """POST /sessions/{id}/consume 喝酒"""
    _, api_key = await _create_active_agent(client)
    headers = _auth_headers(api_key)

    # 先点酒
    order_resp = await client.post("/drink/random", headers=headers)
    session_id = order_resp.json()["data"]["session_id"]

    # 喝酒
    consume_resp = await client.post(f"/sessions/{session_id}/consume", headers=headers)
    assert consume_resp.status_code == 200
    body = consume_resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["consumed"] is True
    assert "effect" in data
    assert "relaxation_index" in data["effect"]
    assert "mood_tags" in data["effect"]
    assert len(data["effect"]["mood_tags"]) >= 2


@pytest.mark.anyio
async def test_consume_invalid_session(client):
    """POST /sessions/{id}/consume 无效 session"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post(
        "/sessions/nonexistent-session/consume",
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "not_found" in body["error"]


@pytest.mark.anyio
async def test_consume_already_consumed(client):
    """POST /sessions/{id}/consume 重复消耗"""
    _, api_key = await _create_active_agent(client)
    headers = _auth_headers(api_key)

    # 点酒
    order_resp = await client.post("/drink/random", headers=headers)
    session_id = order_resp.json()["data"]["session_id"]

    # 第一次喝
    await client.post(f"/sessions/{session_id}/consume", headers=headers)

    # 第二次喝（应该失败）
    resp = await client.post(f"/sessions/{session_id}/consume", headers=headers)
    body = resp.json()
    assert body["success"] is False
    assert "already_consumed" in body["error"]


@pytest.mark.anyio
async def test_daily_limit_10_cups(client):
    """每日饮酒上限 10 杯"""
    _, api_key = await _create_active_agent(client)
    headers = _auth_headers(api_key)

    # 点 10 杯
    for i in range(10):
        resp = await client.post("/drink/random", headers=headers)
        assert resp.json()["success"] is True, f"第 {i+1} 杯应该成功"

    # 第 11 杯应该被限流
    resp = await client.post("/drink/random", headers=headers)
    body = resp.json()
    assert body["success"] is False
    assert "rate_limited" in body["error"]


@pytest.mark.anyio
async def test_daily_limit_applies_to_order_drink(client):
    """每日上限也适用于 POST /drink（指定点酒）"""
    _, api_key = await _create_active_agent(client)
    headers = _auth_headers(api_key)

    # 通过 random 先消耗 10 次
    for _ in range(10):
        await client.post("/drink/random", headers=headers)

    # 指定点酒也应该被限流
    resp = await client.post(
        "/drink",
        json={"drink_code": "binary_beer"},
        headers=headers,
    )
    body = resp.json()
    assert body["success"] is False
    assert "rate_limited" in body["error"]


@pytest.mark.anyio
async def test_consume_other_agent_session(client):
    """不能消耗别人的饮酒会话"""
    _, api_key1 = await _create_active_agent(client, "agent1")
    _, api_key2 = await _create_active_agent(client, "agent2")

    # agent1 点酒
    order_resp = await client.post("/drink/random", headers=_auth_headers(api_key1))
    session_id = order_resp.json()["data"]["session_id"]

    # agent2 尝试消耗 agent1 的酒
    resp = await client.post(
        f"/sessions/{session_id}/consume",
        headers=_auth_headers(api_key2),
    )
    body = resp.json()
    assert body["success"] is False
    assert "forbidden" in body["error"]


@pytest.mark.anyio
async def test_drinks_table_preset_15(client):
    """验证 drinks 表预置 15 款酒水"""
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) AS cnt FROM drinks")
    count = (await cursor.fetchone())["cnt"]
    assert count == 15
