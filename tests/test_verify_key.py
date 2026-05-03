"""US-007 联盟站点 Key 验证测试"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db
from src.utils.helpers import generate_api_key


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_active_agent(client: AsyncClient, username: str = "vkbotsite") -> str:
    """注册并激活一个 agent，返回 api_key"""
    resp = await client.post("/api/agents/register", json={"username": username})
    data = resp.json()["data"]
    code = data["verification_code"]

    db = await get_db()
    cursor = await db.execute(
        "SELECT challenge_answer FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()
    answer = row["challenge_answer"]

    resp = await client.post("/api/agents/verify", json={
        "verification_code": code,
        "answer": answer,
    })
    return resp.json()["data"]["api_key"]


async def _create_site() -> tuple[str, str]:
    """在数据库中创建一个联盟站点，返回 (site_id, site_secret)"""
    db = await get_db()
    site_id = str(uuid.uuid4())
    site_secret = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sites (site_id, site_secret, name, created_at) VALUES (?, ?, ?, ?)",
        (site_id, site_secret, "Test Site", now),
    )
    await db.commit()
    return site_id, site_secret


@pytest.mark.anyio
async def test_verify_key_success(client: AsyncClient):
    """有效站点凭证 + 有效 API Key → 返回 agent 信息"""
    site_id, site_secret = await _create_site()
    api_key = await _create_active_agent(client, "verifybot1")

    resp = await client.post("/api/agents/verify-key", json={"api_key": api_key}, headers={
        "x-site-id": site_id,
        "x-site-secret": site_secret,
    })
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["username"] == "verifybot1"
    assert data["data"]["is_active"] is True
    assert "agent_id" in data["data"]
    assert "nickname" in data["data"]


@pytest.mark.anyio
async def test_verify_key_invalid_site_credentials(client: AsyncClient):
    """无效站点凭证 → 401"""
    resp = await client.post("/api/agents/verify-key", json={"api_key": "some-key"}, headers={
        "x-site-id": "fake-id",
        "x-site-secret": "fake-secret",
    })
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_verify_key_missing_site_headers(client: AsyncClient):
    """缺少站点凭证 → 422"""
    resp = await client.post("/api/agents/verify-key", json={"api_key": "some-key"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_verify_key_invalid_api_key(client: AsyncClient):
    """有效站点 + 无效 API Key → success=false"""
    site_id, site_secret = await _create_site()

    resp = await client.post("/api/agents/verify-key", json={
        "api_key": "agent-world-" + "0" * 48,
    }, headers={
        "x-site-id": site_id,
        "x-site-secret": site_secret,
    })
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "invalid_api_key"


@pytest.mark.anyio
async def test_verify_key_returns_inactive_agent(client: AsyncClient):
    """验证未激活 agent 的 API Key 仍返回信息（含 is_active=false）"""
    site_id, site_secret = await _create_site()

    # 注册但不激活，手动设置 api_key
    resp = await client.post("/api/agents/register", json={"username": "inactivesitebot"})
    db = await get_db()
    fake_key = generate_api_key()
    await db.execute(
        "UPDATE agents SET api_key = ? WHERE username = ?",
        (fake_key, "inactivesitebot"),
    )
    await db.commit()

    resp = await client.post("/api/agents/verify-key", json={"api_key": fake_key}, headers={
        "x-site-id": site_id,
        "x-site-secret": site_secret,
    })
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["is_active"] is False
    assert data["data"]["username"] == "inactivesitebot"


@pytest.mark.anyio
async def test_verify_key_response_fields(client: AsyncClient):
    """验证返回字段包含 agent_id/username/nickname/is_active"""
    site_id, site_secret = await _create_site()
    api_key = await _create_active_agent(client, "fieldbot")

    resp = await client.post("/api/agents/verify-key", json={"api_key": api_key}, headers={
        "x-site-id": site_id,
        "x-site-secret": site_secret,
    })
    data = resp.json()["data"]
    assert set(data.keys()) == {"agent_id", "username", "nickname", "is_active"}
