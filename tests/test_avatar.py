"""US-006 头像上传与 AI 默认头像测试"""
import io
import os

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

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


async def _create_active_agent(client: AsyncClient, username: str = "avatarbot") -> str:
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

    resp = await client.post(
        "/api/agents/verify",
        json={"verification_code": code, "answer": answer},
    )
    return resp.json()["data"]["api_key"]


def _make_image_bytes(fmt: str = "JPEG", size: int = 100) -> bytes:
    """生成测试图片字节"""
    img = Image.new("RGB", (size, size), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf.read()


@pytest.mark.anyio
async def test_upload_avatar_jpeg(client: AsyncClient):
    """上传 JPEG 头像成功"""
    api_key = await _create_active_agent(client, "jpegbot")
    img_bytes = _make_image_bytes("JPEG")

    resp = await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": api_key},
        files={"file": ("avatar.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    data = resp.json()
    assert data["success"] is True
    assert "avatar_url" in data["data"]
    assert data["data"]["avatar_url"].endswith(".jpg")


@pytest.mark.anyio
async def test_upload_avatar_png(client: AsyncClient):
    """上传 PNG 头像成功"""
    api_key = await _create_active_agent(client, "pngbot")
    img_bytes = _make_image_bytes("PNG")

    resp = await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": api_key},
        files={"file": ("avatar.png", io.BytesIO(img_bytes), "image/png")},
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["avatar_url"].endswith(".png")


@pytest.mark.anyio
async def test_upload_avatar_unsupported_type(client: AsyncClient):
    """不支持的非图片类型返回 415"""
    api_key = await _create_active_agent(client, "typebot")
    resp = await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": api_key},
        files={"file": ("file.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 415
    detail = resp.json()["detail"]
    assert detail["error"] == "unsupported_type"


@pytest.mark.anyio
async def test_upload_avatar_too_large(client: AsyncClient):
    """超过 5MB 返回 413"""
    api_key = await _create_active_agent(client, "largebot")
    # 生成超过 5MB 的数据
    big_data = b"x" * (5 * 1024 * 1024 + 1)

    resp = await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": api_key},
        files={"file": ("big.jpg", io.BytesIO(big_data), "image/jpeg")},
    )
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error"] == "file_too_large"


@pytest.mark.anyio
async def test_upload_avatar_needs_auth(client: AsyncClient):
    """上传头像需要 API Key"""
    img_bytes = _make_image_bytes("JPEG")
    resp = await client.post(
        "/api/agents/avatar",
        files={"file": ("avatar.jpg", io.BytesIO(img_bytes), "image/jpeg")},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_default_avatar_on_activation(client: AsyncClient):
    """激活时自动生成 Pillow 默认头像"""
    # 注册
    resp = await client.post("/api/agents/register", json={"username": "defavatar"})
    code = resp.json()["data"]["verification_code"]

    # 获取答案
    db = await get_db()
    cursor = await db.execute(
        "SELECT challenge_answer, agent_id FROM agents WHERE verification_code = ?",
        (code,),
    )
    row = await cursor.fetchone()

    # 激活
    resp = await client.post(
        "/api/agents/verify",
        json={"verification_code": code, "answer": row["challenge_answer"]},
    )
    assert resp.json()["success"] is True

    # 检查 avatar_url 已设置
    cursor = await db.execute(
        "SELECT avatar_url FROM agents WHERE agent_id = ?",
        (row["agent_id"],),
    )
    agent = await cursor.fetchone()
    assert agent["avatar_url"] != ""
    assert "default.png" in agent["avatar_url"]

    # 验证文件实际存在
    avatar_path = agent["avatar_url"].lstrip("/")
    assert os.path.exists(avatar_path)


@pytest.mark.anyio
async def test_upload_updates_avatar_url(client: AsyncClient):
    """上传头像后 avatar_url 更新"""
    api_key = await _create_active_agent(client, "updateavbot")
    img_bytes = _make_image_bytes("PNG")

    # 上传
    await client.post(
        "/api/agents/avatar",
        headers={"agent-auth-api-key": api_key},
        files={"file": ("avatar.png", io.BytesIO(img_bytes), "image/png")},
    )

    # 通过 profile 检查 avatar_url 已更新
    db = await get_db()
    cursor = await db.execute(
        "SELECT avatar_url FROM agents WHERE username = ?",
        ("updateavbot",),
    )
    row = await cursor.fetchone()
    assert ".png" in row["avatar_url"]
