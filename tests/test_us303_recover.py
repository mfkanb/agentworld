"""US-303 API Key找回功能 测试"""
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
    db = await get_db()
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "recoveruser") -> tuple[str, str]:
    """注册并激活 agent，返回 (agent_id, api_key)"""
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
async def test_recover_success(client: AsyncClient):
    """通过 username 找回，生成挑战题"""
    await _create_active_agent(client, "recover_test_user")

    resp = await client.post("/api/agents/recover", json={"username": "recover_test_user"})
    data = resp.json()
    assert data["success"] is True
    assert "verification_code" in data["data"]
    assert "challenge_text" in data["data"]


@pytest.mark.anyio
async def test_recover_user_not_found(client: AsyncClient):
    """username 不存在返回 404"""
    resp = await client.post("/api/agents/recover", json={"username": "nonexistent"})
    data = resp.json()
    assert data["success"] is False
    assert "not_found" in data["error"]


@pytest.mark.anyio
async def test_recover_inactive_account(client: AsyncClient):
    """未激活的账号不能找回"""
    # 注册但不激活
    await client.post("/api/agents/register", json={"username": "inactive_user"})

    resp = await client.post("/api/agents/recover", json={"username": "inactive_user"})
    data = resp.json()
    assert data["success"] is False
    assert "not_active" in data["error"]


@pytest.mark.anyio
async def test_verify_recover_returns_original_api_key(client: AsyncClient):
    """验证成功后返回原有 API Key（不生成新 Key）"""
    _, original_api_key = await _create_active_agent(client, "original_key_user")

    # 发起找回
    resp = await client.post("/api/agents/recover", json={"username": "original_key_user"})
    recover_data = resp.json()["data"]
    code = recover_data["verification_code"]

    # 获取答案
    db = await get_db()
    cursor = await db.execute(
        "SELECT challenge_answer FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()

    # 验证找回
    resp = await client.post("/api/agents/verify-recover", json={
        "verification_code": code,
        "answer": row["challenge_answer"],
    })
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["api_key"] == original_api_key


@pytest.mark.anyio
async def test_verify_recover_wrong_answer(client: AsyncClient):
    """答案错误返回剩余次数"""
    await _create_active_agent(client, "wrong_answer_user")

    resp = await client.post("/api/agents/recover", json={"username": "wrong_answer_user"})
    code = resp.json()["data"]["verification_code"]

    resp = await client.post("/api/agents/verify-recover", json={
        "verification_code": code,
        "answer": "99999",
    })
    data = resp.json()
    assert data["success"] is False
    assert "wrong_answer" in data["error"]
    assert "剩余" in data["message"]


@pytest.mark.anyio
async def test_verify_recover_5_attempts(client: AsyncClient):
    """5次失败限制"""
    await _create_active_agent(client, "max_attempts_user")

    resp = await client.post("/api/agents/recover", json={"username": "max_attempts_user"})
    code = resp.json()["data"]["verification_code"]

    for i in range(5):
        resp = await client.post("/api/agents/verify-recover", json={
            "verification_code": code,
            "answer": f"9999{i}",
        })

    data = resp.json()
    assert data["success"] is False
    assert "max_attempts" in data["error"]

    # 验证码应被清除
    db = await get_db()
    cursor = await db.execute(
        "SELECT verification_code FROM agents WHERE username = 'max_attempts_user'",
    )
    row = await cursor.fetchone()
    assert row["verification_code"] == ""


@pytest.mark.anyio
async def test_verify_recover_invalid_code(client: AsyncClient):
    """无效验证码"""
    resp = await client.post("/api/agents/verify-recover", json={
        "verification_code": "nonexistent-code",
        "answer": "42",
    })
    data = resp.json()
    assert data["success"] is False
    assert "invalid_code" in data["error"]
