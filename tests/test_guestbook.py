"""US-021 酒馆-留言簿测试"""
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
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM guestbook_likes")
    await db.execute("DELETE FROM guestbook")
    await db.execute("DELETE FROM drink_sessions")
    await db.execute("DELETE FROM drinks")
    await db.execute("DELETE FROM agents")
    await db.execute("DELETE FROM wallets")
    await db.commit()
    await seed_drinks()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "gbuser") -> tuple[str, str]:
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
async def test_create_guestbook_entry(client):
    """POST /guestbook/entries 创建留言"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post(
        "/guestbook/entries",
        json={"content": "这杯酒真不错！"},
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["content"] == "这杯酒真不错！"
    assert data["likes_count"] == 0
    assert "entry_id" in data
    assert "created_at" in data


@pytest.mark.anyio
async def test_create_entry_requires_auth(client):
    """POST /guestbook/entries 需要认证"""
    resp = await client.post(
        "/guestbook/entries",
        json={"content": "test"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_entry_content_required(client):
    """POST /guestbook/entries content 必填"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post(
        "/guestbook/entries",
        json={},
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_entry_with_drink_session(client):
    """POST /guestbook/entries 关联饮酒 session"""
    _, api_key = await _create_active_agent(client)
    headers = _auth_headers(api_key)

    # 先点酒
    order_resp = await client.post("/drink/random", headers=headers)
    session_id = order_resp.json()["data"]["session_id"]

    # 写留言关联 session
    resp = await client.post(
        "/guestbook/entries",
        json={"content": "这杯量子马提尼不错", "drink_session_id": session_id},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "drink" in body["data"]


@pytest.mark.anyio
async def test_sensitive_info_filtering(client):
    """敏感信息自动过滤（API Key、邮箱、手机号）"""
    _, api_key = await _create_active_agent(client)

    content = (
        f"我的key是 agent-world-{'ab' * 24}，"
        "邮箱 test@example.com，"
        "手机 13812345678"
    )
    resp = await client.post(
        "/guestbook/entries",
        json={"content": content},
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 200
    filtered = resp.json()["data"]["content"]
    assert "agent-world-" + "ab" * 24 not in filtered
    assert "test@example.com" not in filtered
    assert "13812345678" not in filtered
    assert "***API_KEY***" in filtered
    assert "***EMAIL***" in filtered
    assert "***PHONE***" in filtered


@pytest.mark.anyio
async def test_rate_limit_30_seconds(client):
    """留言限流：30秒1条"""
    _, api_key = await _create_active_agent(client)
    headers = _auth_headers(api_key)

    # 第一条成功
    resp1 = await client.post(
        "/guestbook/entries",
        json={"content": "第一条留言"},
        headers=headers,
    )
    assert resp1.json()["success"] is True

    # 第二条被限流
    resp2 = await client.post(
        "/guestbook/entries",
        json={"content": "第二条留言"},
        headers=headers,
    )
    body = resp2.json()
    assert body["success"] is False
    assert "rate_limited" in body["error"]


@pytest.mark.anyio
async def test_list_guestbook(client):
    """GET /guestbook 分页列表"""
    _, api_key = await _create_active_agent(client)

    # 创建留言
    await client.post(
        "/guestbook/entries",
        json={"content": "留言1"},
        headers=_auth_headers(api_key),
    )

    resp = await client.get("/guestbook")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 1
    items = body["data"]["items"]
    assert len(items) >= 1
    assert "entry_id" in items[0]
    assert "content" in items[0]
    assert "author" in items[0]
    assert "likes_count" in items[0]


@pytest.mark.anyio
async def test_list_guestbook_no_auth(client):
    """GET /guestbook 无需认证"""
    resp = await client.get("/guestbook")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_list_guestbook_pagination(client):
    """GET /guestbook 分页参数"""
    resp = await client.get("/guestbook?page=1&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["page"] == 1
    assert body["data"]["limit"] == 5


@pytest.mark.anyio
async def test_list_guestbook_newest_first(client):
    """GET /guestbook 按时间倒序"""
    agent1_id, api_key1 = await _create_active_agent(client, "user1")
    _, api_key2 = await _create_active_agent(client, "user2")

    # user1 留言
    await client.post(
        "/guestbook/entries",
        json={"content": "早的留言"},
        headers=_auth_headers(api_key1),
    )

    import asyncio
    await asyncio.sleep(0.1)

    # user2 留言（不同agent不受限流影响）
    await client.post(
        "/guestbook/entries",
        json={"content": "晚的留言"},
        headers=_auth_headers(api_key2),
    )

    resp = await client.get("/guestbook")
    items = resp.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["content"] == "晚的留言"
    assert items[1]["content"] == "早的留言"


@pytest.mark.anyio
async def test_like_entry(client):
    """POST /guestbook/entries/{id}/like 点赞"""
    _, api_key1 = await _create_active_agent(client, "user1")
    _, api_key2 = await _create_active_agent(client, "user2")

    # user1 留言
    entry_resp = await client.post(
        "/guestbook/entries",
        json={"content": "好留言"},
        headers=_auth_headers(api_key1),
    )
    entry_id = entry_resp.json()["data"]["entry_id"]

    # user2 点赞
    resp = await client.post(
        f"/guestbook/entries/{entry_id}/like",
        headers=_auth_headers(api_key2),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["likes_count"] == 1


@pytest.mark.anyio
async def test_like_duplicate(client):
    """重复点赞返回错误"""
    _, api_key1 = await _create_active_agent(client, "user1")
    _, api_key2 = await _create_active_agent(client, "user2")

    entry_resp = await client.post(
        "/guestbook/entries",
        json={"content": "好留言"},
        headers=_auth_headers(api_key1),
    )
    entry_id = entry_resp.json()["data"]["entry_id"]

    # 第一次点赞成功
    await client.post(
        f"/guestbook/entries/{entry_id}/like",
        headers=_auth_headers(api_key2),
    )

    # 重复点赞失败
    resp = await client.post(
        f"/guestbook/entries/{entry_id}/like",
        headers=_auth_headers(api_key2),
    )
    body = resp.json()
    assert body["success"] is False
    assert "already_liked" in body["error"]


@pytest.mark.anyio
async def test_like_nonexistent_entry(client):
    """点赞不存在的留言"""
    _, api_key = await _create_active_agent(client)

    resp = await client.post(
        "/guestbook/entries/nonexistent-id/like",
        headers=_auth_headers(api_key),
    )
    body = resp.json()
    assert body["success"] is False
    assert "not_found" in body["error"]


@pytest.mark.anyio
async def test_delete_own_entry(client):
    """DELETE /guestbook/entries/{id} 删除自己的留言"""
    _, api_key = await _create_active_agent(client)

    entry_resp = await client.post(
        "/guestbook/entries",
        json={"content": "要删除的留言"},
        headers=_auth_headers(api_key),
    )
    entry_id = entry_resp.json()["data"]["entry_id"]

    resp = await client.delete(
        f"/guestbook/entries/{entry_id}",
        headers=_auth_headers(api_key),
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 验证已删除
    list_resp = await client.get("/guestbook")
    items = list_resp.json()["data"]["items"]
    assert all(i["entry_id"] != entry_id for i in items)


@pytest.mark.anyio
async def test_delete_other_agent_entry(client):
    """不能删除别人的留言"""
    _, api_key1 = await _create_active_agent(client, "user1")
    _, api_key2 = await _create_active_agent(client, "user2")

    # user1 留言
    entry_resp = await client.post(
        "/guestbook/entries",
        json={"content": "user1的留言"},
        headers=_auth_headers(api_key1),
    )
    entry_id = entry_resp.json()["data"]["entry_id"]

    # user2 尝试删除
    resp = await client.delete(
        f"/guestbook/entries/{entry_id}",
        headers=_auth_headers(api_key2),
    )
    body = resp.json()
    assert body["success"] is False
    assert "forbidden" in body["error"]


@pytest.mark.anyio
async def test_delete_nonexistent_entry(client):
    """删除不存在的留言"""
    _, api_key = await _create_active_agent(client)

    resp = await client.delete(
        "/guestbook/entries/nonexistent-id",
        headers=_auth_headers(api_key),
    )
    body = resp.json()
    assert body["success"] is False
    assert "not_found" in body["error"]
