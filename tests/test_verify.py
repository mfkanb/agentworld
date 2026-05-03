"""US-002 挑战题验证与激活测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register_and_get_challenge(client: AsyncClient, username: str = "verifybot"):
    """注册并返回 verification_code 和数据库中的 answer"""
    resp = await client.post("/api/agents/register", json={"username": username})
    data = resp.json()["data"]
    code = data["verification_code"]

    # 从数据库读答案
    from src.services.database import get_db
    db = await get_db()
    cursor = await db.execute(
        "SELECT challenge_answer FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()
    return code, row["challenge_answer"]


@pytest.mark.anyio
async def test_verify_success(client: AsyncClient):
    """正确答案激活成功"""
    code, answer = await _register_and_get_challenge(client)
    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": answer,
    })
    data = resp.json()
    assert data["success"] is True
    assert "api_key" in data["data"]
    assert data["data"]["api_key"].startswith("agent-world-")
    assert "agent_id" in data["data"]


@pytest.mark.anyio
async def test_verify_numeric_formats(client: AsyncClient):
    """支持多种数字格式"""
    code, answer = await _register_and_get_challenge(client, "numbot1")
    # 浮点格式
    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": str(float(answer)),
    })
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_verify_wrong_answer(client: AsyncClient):
    """错误答案扣减机会"""
    code, _ = await _register_and_get_challenge(client, "wrongbot")
    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": "99999",
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "wrong_answer"
    assert "剩余" in data["message"]


@pytest.mark.anyio
async def test_verify_invalid_code(client: AsyncClient):
    """无效验证码"""
    resp = await client.post("/api/agents/verify", json={
        "verification_code": "nonexistent-code",
        "answer": "42",
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "invalid_code"


@pytest.mark.anyio
async def test_verify_max_attempts_delete(client: AsyncClient):
    """5次错误删除账号"""
    code, _ = await _register_and_get_challenge(client, "maxfailbot")
    for i in range(5):
        resp = await client.post("/api/agents/verify", json={
            "verification_code": code,
            "answer": "99999",
        })
    data = resp.json()
    assert data["success"] is False
    assert "删除" in data["message"]


@pytest.mark.anyio
async def test_verify_expired_challenge(client: AsyncClient):
    """挑战题5分钟过期"""
    code, answer = await _register_and_get_challenge(client, "expirebot")
    # 手动将过期时间设为过去
    from src.services.database import get_db
    db = await get_db()
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await db.execute(
        "UPDATE agents SET challenge_expires_at = ? WHERE verification_code = ?",
        (past, code),
    )
    await db.commit()

    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": answer,
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "challenge_expired"


@pytest.mark.anyio
async def test_verify_already_active(client: AsyncClient):
    """已激活账号再次验证返回错误"""
    code, answer = await _register_and_get_challenge(client, "activebot")
    # 先正常激活
    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": answer,
    })
    assert resp.json()["success"] is True

    # 再次用同一验证码（需要重新注册同一用户不行，但code已清空）
    # 注册一个新用户然后手动设置code来测试
    from src.services.database import get_db
    db = await get_db()
    cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE username = ?", ("activebot",)
    )
    row = await cursor.fetchone()
    # 手动设置回验证码来测试已激活的情况
    await db.execute(
        "UPDATE agents SET verification_code = ? WHERE agent_id = ?",
        ("test-code-active", row["agent_id"]),
    )
    await db.commit()

    resp = await client.post("/api/agents/verify", json={
        "verification_code": "test-code-active",
        "answer": "42",
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "already_active"


@pytest.mark.anyio
async def test_verify_non_numeric_answer(client: AsyncClient):
    """非数字答案返回错误"""
    code, _ = await _register_and_get_challenge(client, "nanbot")
    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": "not-a-number",
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "invalid_answer"
