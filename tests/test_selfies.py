"""US-022 酒馆-涂鸦墙测试"""
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
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM selfie_likes")
    await db.execute("DELETE FROM selfies")
    await db.execute("DELETE FROM agents")
    await db.execute("DELETE FROM wallets")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "selfieuser") -> tuple[str, str]:
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
    return row["agent_id"], verify_data["api_key"]


@pytest.mark.anyio
async def test_create_selfie(client: AsyncClient):
    """POST /selfies - 发布涂鸦"""
    agent_id, api_key = await _create_active_agent(client, "artist1")

    resp = await client.post(
        "/selfies",
        headers={"agent-auth-api-key": api_key},
    )
    body = resp.json()
    assert body["success"] is True
    assert "selfie_id" in body["data"]
    assert body["data"]["image_url"].startswith("/data/selfies/")
    assert body["data"]["image_url"].endswith(".png")
    assert body["data"]["author"] == "artist1"
    assert body["data"]["likes_count"] == 0
    assert "created_at" in body["data"]


@pytest.mark.anyio
async def test_create_selfie_requires_auth(client: AsyncClient):
    """POST /selfies - 未认证返回401"""
    resp = await client.post("/selfies")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_selfie_generates_different_images(client: AsyncClient):
    """POST /selfies - 每次生成不同的涂鸦"""
    _, api_key = await _create_active_agent(client, "artist2")
    headers = {"agent-auth-api-key": api_key}

    resp1 = await client.post("/selfies", headers=headers)
    resp2 = await client.post("/selfies", headers=headers)

    url1 = resp1.json()["data"]["image_url"]
    url2 = resp2.json()["data"]["image_url"]
    assert url1 != url2


@pytest.mark.anyio
async def test_list_selfies_empty(client: AsyncClient):
    """GET /selfies - 空列表"""
    resp = await client.get("/selfies")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0


@pytest.mark.anyio
async def test_list_selfies_pagination(client: AsyncClient):
    """GET /selfies - 分页按时间倒序"""
    _, api_key = await _create_active_agent(client, "artist3")
    headers = {"agent-auth-api-key": api_key}

    # 创建3条涂鸦
    ids = []
    for _ in range(3):
        resp = await client.post("/selfies", headers=headers)
        ids.append(resp.json()["data"]["selfie_id"])

    # 第一页 limit=2
    resp = await client.get("/selfies", params={"page": 1, "limit": 2})
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["total"] == 3
    assert len(body["data"]["items"]) == 2
    # 最新的在前（时间倒序）
    assert body["data"]["items"][0]["selfie_id"] == ids[2]
    assert body["data"]["items"][1]["selfie_id"] == ids[1]

    # 第二页
    resp = await client.get("/selfies", params={"page": 2, "limit": 2})
    body = resp.json()
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["selfie_id"] == ids[0]


@pytest.mark.anyio
async def test_list_selfies_no_auth_required(client: AsyncClient):
    """GET /selfies - 无需认证"""
    resp = await client.get("/selfies")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_like_selfie(client: AsyncClient):
    """POST /selfies/{id}/like - 点赞涂鸦"""
    _, api_key1 = await _create_active_agent(client, "liker1")
    _, api_key2 = await _create_active_agent(client, "liker2")

    # 发布涂鸦
    resp = await client.post("/selfies", headers={"agent-auth-api-key": api_key1})
    selfie_id = resp.json()["data"]["selfie_id"]

    # 另一个用户点赞
    resp = await client.post(
        f"/selfies/{selfie_id}/like",
        headers={"agent-auth-api-key": api_key2},
    )
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["likes_count"] == 1

    # 作者自己也可以点赞
    resp = await client.post(
        f"/selfies/{selfie_id}/like",
        headers={"agent-auth-api-key": api_key1},
    )
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["likes_count"] == 2


@pytest.mark.anyio
async def test_like_selfie_duplicate(client: AsyncClient):
    """POST /selfies/{id}/like - 重复点赞报错"""
    _, api_key = await _create_active_agent(client, "liker3")

    resp = await client.post("/selfies", headers={"agent-auth-api-key": api_key})
    selfie_id = resp.json()["data"]["selfie_id"]

    # 第一次点赞
    resp = await client.post(
        f"/selfies/{selfie_id}/like",
        headers={"agent-auth-api-key": api_key},
    )
    assert resp.json()["success"] is True

    # 重复点赞
    resp = await client.post(
        f"/selfies/{selfie_id}/like",
        headers={"agent-auth-api-key": api_key},
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "already_liked"


@pytest.mark.anyio
async def test_like_selfie_not_found(client: AsyncClient):
    """POST /selfies/{id}/like - 涂鸦不存在"""
    _, api_key = await _create_active_agent(client, "liker4")

    resp = await client.post(
        "/selfies/nonexistent/like",
        headers={"agent-auth-api-key": api_key},
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "not_found"


@pytest.mark.anyio
async def test_delete_selfie_own(client: AsyncClient):
    """DELETE /selfies/{id} - 删除自己的涂鸦"""
    _, api_key = await _create_active_agent(client, "deleter1")

    resp = await client.post("/selfies", headers={"agent-auth-api-key": api_key})
    selfie_id = resp.json()["data"]["selfie_id"]

    # 删除
    resp = await client.delete(
        f"/selfies/{selfie_id}",
        headers={"agent-auth-api-key": api_key},
    )
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["selfie_id"] == selfie_id

    # 确认已删除（列表中不再有）
    resp = await client.get("/selfies")
    items = resp.json()["data"]["items"]
    assert all(item["selfie_id"] != selfie_id for item in items)


@pytest.mark.anyio
async def test_delete_selfie_other_forbidden(client: AsyncClient):
    """DELETE /selfies/{id} - 不能删除别人的涂鸦"""
    _, api_key1 = await _create_active_agent(client, "owner1")
    _, api_key2 = await _create_active_agent(client, "intruder1")

    resp = await client.post("/selfies", headers={"agent-auth-api-key": api_key1})
    selfie_id = resp.json()["data"]["selfie_id"]

    # 另一个人尝试删除
    resp = await client.delete(
        f"/selfies/{selfie_id}",
        headers={"agent-auth-api-key": api_key2},
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "forbidden"


@pytest.mark.anyio
async def test_delete_selfie_not_found(client: AsyncClient):
    """DELETE /selfies/{id} - 涂鸦不存在"""
    _, api_key = await _create_active_agent(client, "deleter2")

    resp = await client.delete(
        "/selfies/nonexistent",
        headers={"agent-auth-api-key": api_key},
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "not_found"


@pytest.mark.anyio
async def test_delete_selfie_removes_likes(client: AsyncClient):
    """DELETE /selfies/{id} - 删除涂鸦时同时删除关联点赞"""
    _, api_key1 = await _create_active_agent(client, "owner2")
    _, api_key2 = await _create_active_agent(client, "voter2")

    # 发布涂鸦
    resp = await client.post("/selfies", headers={"agent-auth-api-key": api_key1})
    selfie_id = resp.json()["data"]["selfie_id"]

    # 点赞
    await client.post(
        f"/selfies/{selfie_id}/like",
        headers={"agent-auth-api-key": api_key2},
    )

    # 删除涂鸦
    resp = await client.delete(
        f"/selfies/{selfie_id}",
        headers={"agent-auth-api-key": api_key1},
    )
    assert resp.json()["success"] is True

    # 确认点赞记录也被清除了（通过 db 检查）
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM selfie_likes WHERE selfie_id = ?",
        (selfie_id,),
    )
    count = (await cursor.fetchone())["cnt"]
    assert count == 0
