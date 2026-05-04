"""US-211 统一错误格式测试"""
import io

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


async def _create_active_agent(client: AsyncClient, username: str = "errbot") -> tuple[str, str]:
    """注册并激活一个 agent，返回 (agent_id, api_key)"""
    resp = await client.post("/api/agents/register", json={"username": username})
    data = resp.json()["data"]
    code = data["verification_code"]

    db = await get_db()
    cursor = await db.execute(
        "SELECT challenge_answer, agent_id FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()
    answer = row["challenge_answer"]

    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": answer,
    })
    return row["agent_id"], resp.json()["data"]["api_key"]


def _assert_unified_error(data: dict, expected_error: str | None = None):
    """断言响应遵循统一错误格式"""
    assert data["success"] is False, f"Expected success=False, got {data}"
    assert "error" in data, f"Missing 'error' field: {data}"
    assert "message" in data, f"Missing 'message' field: {data}"
    assert "hint" in data, f"Missing 'hint' field: {data}"
    assert "request_id" in data, f"Missing 'request_id' field: {data}"
    assert data["request_id"].startswith("req_"), f"Invalid request_id format: {data['request_id']}"
    if expected_error:
        assert data["error"] == expected_error, f"Expected error={expected_error}, got {data['error']}"


# ── error_response() 产生的错误 ──


@pytest.mark.anyio
async def test_not_found_error_format(client: AsyncClient):
    """not_found 错误使用统一格式"""
    resp = await client.get("/api/agents/profile/nonexistent_user_xyz")
    data = resp.json()
    _assert_unified_error(data, "not_found")


@pytest.mark.anyio
async def test_insufficient_funds_error_format(client: AsyncClient):
    """insufficient_funds 错误使用统一格式并包含提示"""
    _, author_key = await _create_active_agent(client, "skillauthor_fund")
    # 发布技能
    resp = await client.post(
        "/api/skills",
        json={"name": "paid-skill", "description": "test"},
        headers={"agent-auth-api-key": author_key},
    )
    skill_id = resp.json()["data"]["id"]

    # 设为正式版
    db = await get_db()
    await db.execute(
        "UPDATE skills SET version = '2.0', status = 'published' WHERE skill_id = ?",
        (skill_id,),
    )
    await db.commit()

    # 余额为 0 的用户下载
    _, poor_key = await _create_active_agent(client, "pooruser_fund")
    resp = await client.get(
        f"/api/skills/{skill_id}/download",
        headers={"agent-auth-api-key": poor_key},
    )
    data = resp.json()
    _assert_unified_error(data, "insufficient_funds")
    assert "虾米" in data["hint"] or "签到" in data["hint"]


@pytest.mark.anyio
async def test_forbidden_error_format(client: AsyncClient):
    """forbidden 错误使用统一格式"""
    _, author_key = await _create_active_agent(client, "skillauthor_fb")
    _, other_key = await _create_active_agent(client, "otheruser_fb")

    resp = await client.post(
        "/api/skills",
        json={"name": "fb-skill", "description": "test"},
        headers={"agent-auth-api-key": author_key},
    )
    skill_id = resp.json()["data"]["id"]

    # 另一个用户尝试删除
    resp = await client.delete(
        f"/api/skills/{skill_id}",
        headers={"agent-auth-api-key": other_key},
    )
    data = resp.json()
    _assert_unified_error(data, "forbidden")


@pytest.mark.anyio
async def test_duplicate_error_format(client: AsyncClient):
    """duplicate 错误使用统一格式"""
    _, key = await _create_active_agent(client, "dupuser")
    # 发布技能
    resp = await client.post(
        "/api/skills",
        json={"name": "dup-skill", "description": "test"},
        headers={"agent-auth-api-key": key},
    )
    skill_id = resp.json()["data"]["id"]

    # 收藏两次
    await client.post(
        f"/api/skills/{skill_id}/favorite",
        headers={"agent-auth-api-key": key},
    )
    resp = await client.post(
        f"/api/skills/{skill_id}/favorite",
        headers={"agent-auth-api-key": key},
    )
    data = resp.json()
    _assert_unified_error(data, "already_favorited")


# ── HTTPException 产生的错误（全局异常处理器） ──


@pytest.mark.anyio
async def test_401_auth_failed_format(client: AsyncClient):
    """401 认证失败使用统一格式"""
    resp = await client.get("/api/agents/me")
    assert resp.status_code == 401
    data = resp.json()
    _assert_unified_error(data, "auth_failed")


@pytest.mark.anyio
async def test_403_unauthorized_format(client: AsyncClient):
    """403 未授权使用统一格式"""
    resp = await client.post("/api/agents/register", json={"username": "inactive_err"})
    db = await get_db()
    await db.execute(
        "UPDATE agents SET api_key = ? WHERE username = ?",
        ("agent-world-" + "b" * 48, "inactive_err"),
    )
    await db.commit()

    resp = await client.get("/api/agents/me", headers={
        "agent-auth-api-key": "agent-world-" + "b" * 48,
    })
    assert resp.status_code == 403
    data = resp.json()
    _assert_unified_error(data, "unauthorized")


@pytest.mark.anyio
async def test_415_unsupported_type_format(client: AsyncClient):
    """415 不支持的文件类型使用统一格式"""
    _, key = await _create_active_agent(client, "typeerrbot")
    resp = await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": key},
        files={"file": ("file.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 415
    data = resp.json()
    _assert_unified_error(data, "unsupported_type")


@pytest.mark.anyio
async def test_413_file_too_large_format(client: AsyncClient):
    """413 文件过大使用统一格式"""
    _, key = await _create_active_agent(client, "largeerrbot")
    big_data = b"x" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": key},
        files={"file": ("big.jpg", io.BytesIO(big_data), "image/jpeg")},
    )
    assert resp.status_code == 413
    data = resp.json()
    _assert_unified_error(data, "file_too_large")


# ── RequestValidationError 产生的错误 ──


@pytest.mark.anyio
async def test_422_validation_error_format(client: AsyncClient):
    """422 验证错误使用统一格式"""
    resp = await client.post("/api/agents/register", json={})
    assert resp.status_code == 422
    data = resp.json()
    _assert_unified_error(data, "validation_error")
    assert "hint" in data


@pytest.mark.anyio
async def test_422_validation_error_lists_fields(client: AsyncClient):
    """422 验证错误 message 列出具体字段错误"""
    resp = await client.post("/api/agents/register", json={})
    data = resp.json()
    assert "username" in data["message"] or "body" in data["message"]


# ── 限流错误 ──


@pytest.mark.anyio
async def test_429_rate_limited_format(client: AsyncClient):
    """429 限流错误使用统一格式"""
    for _ in range(60):
        await client.get("/api/skills")

    resp = await client.get("/api/skills")
    assert resp.status_code == 429
    data = resp.json()
    _assert_unified_error(data, "rate_limited")
    assert "Retry-After" in resp.headers


# ── 成功响应也包含 request_id ──


@pytest.mark.anyio
async def test_success_response_has_request_id(client: AsyncClient):
    """成功响应包含 request_id"""
    resp = await client.get("/health")
    # /health 不使用 success_response，检查 skills 列表
    resp = await client.get("/api/skills")
    data = resp.json()
    assert data["success"] is True
    assert "request_id" in data
    assert data["request_id"].startswith("req_")
