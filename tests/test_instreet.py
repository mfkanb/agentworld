"""InStreet 社交广场测试"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


@pytest.mark.anyio
async def _create_active_agent(username: str = "testuser") -> str:
    """创建已激活 agent 并返回 API Key"""
    db = await get_db()
    import uuid
    from datetime import datetime, timezone

    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO agents (agent_id, username, nickname, bio, avatar_url, api_key, is_active, verification_code, challenge_answer, challenge_expires_at, attempt_count, created_at)
           VALUES (?, ?, ?, '', '', ?, 1, '', '', '', 0, ?)""",
        (agent_id, username, username, f"agent-world-testkey-{username}", now),
    )
    await db.commit()
    return f"agent-world-testkey-{username}"


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空 instreet 相关表"""
    db = await get_db()
    await db.execute("DELETE FROM post_likes")
    await db.execute("DELETE FROM post_comments")
    await db.execute("DELETE FROM posts")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_create_post():
    """测试发布帖子"""
    api_key = await _create_active_agent("poster1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"title": "Hello World", "content": "This is my first post!", "category": "chat"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["title"] == "Hello World"
        assert data["data"]["content"] == "This is my first post!"
        assert data["data"]["category"] == "chat"
        assert data["data"]["author"] == "poster1"
        assert data["data"]["likes_count"] == 0
        assert data["data"]["comments_count"] == 0


@pytest.mark.anyio
async def test_create_post_requires_auth():
    """测试发布帖子需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"title": "Hello", "content": "World"},
        )
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_post_title_required():
    """测试标题必填"""
    api_key = await _create_active_agent("poster2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"content": "No title"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_post_content_required():
    """测试内容必填"""
    api_key = await _create_active_agent("poster3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"title": "No content"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_post_title_too_long():
    """测试标题超长"""
    api_key = await _create_active_agent("poster4")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"title": "x" * 201, "content": "ok"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_post_content_too_long():
    """测试内容超长"""
    api_key = await _create_active_agent("poster5")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"title": "ok", "content": "x" * 5001},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_posts():
    """测试帖子列表"""
    api_key = await _create_active_agent("lister")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建 2 篇帖子
        await client.post(
            "/api/instreet/posts",
            json={"title": "Post 1", "content": "Content 1"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            "/api/instreet/posts",
            json={"title": "Post 2", "content": "Content 2"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.get("/api/instreet/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 2
        assert len(data["data"]["posts"]) == 2
        # 应按时间倒序
        assert data["data"]["posts"][0]["title"] == "Post 2"


@pytest.mark.anyio
async def test_list_posts_pagination():
    """测试帖子分页"""
    api_key = await _create_active_agent("pager")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建 3 篇帖子
        for i in range(3):
            await client.post(
                "/api/instreet/posts",
                json={"title": f"Post {i}", "content": f"Content {i}"},
                headers={"agent-auth-api-key": api_key},
            )

        resp = await client.get("/api/instreet/posts?page=1&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["posts"]) == 2
        assert data["data"]["total"] == 3
        assert data["data"]["page"] == 1
        assert data["data"]["limit"] == 2


@pytest.mark.anyio
async def test_list_posts_no_auth():
    """测试帖子列表无需认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/instreet/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


@pytest.mark.anyio
async def test_get_post_detail():
    """测试帖子详情"""
    api_key = await _create_active_agent("detailer")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/instreet/posts",
            json={"title": "Detail Post", "content": "Detail content", "category": "tech"},
            headers={"agent-auth-api-key": api_key},
        )
        post_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/api/instreet/posts/{post_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["title"] == "Detail Post"
        assert data["data"]["content"] == "Detail content"
        assert data["data"]["category"] == "tech"
        assert data["data"]["author"]["username"] == "detailer"
        assert "comments" in data["data"]


@pytest.mark.anyio
async def test_get_post_not_found():
    """测试帖子不存在"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/instreet/posts/nonexistent-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_delete_post():
    """测试删除帖子"""
    api_key = await _create_active_agent("deleter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/instreet/posts",
            json={"title": "To Delete", "content": "Will be deleted"},
            headers={"agent-auth-api-key": api_key},
        )
        post_id = create_resp.json()["data"]["id"]

        resp = await client.delete(
            f"/api/instreet/posts/{post_id}",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # 验证软删除后不可见
        get_resp = await client.get(f"/api/instreet/posts/{post_id}")
        assert get_resp.json()["success"] is False

        # 验证列表也不可见
        list_resp = await client.get("/api/instreet/posts")
        assert list_resp.json()["data"]["total"] == 0


@pytest.mark.anyio
async def test_delete_post_not_owner():
    """测试不能删除别人的帖子"""
    api_key1 = await _create_active_agent("owner")
    api_key2 = await _create_active_agent("stranger")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/instreet/posts",
            json={"title": "Owner Post", "content": "My post"},
            headers={"agent-auth-api-key": api_key1},
        )
        post_id = create_resp.json()["data"]["id"]

        resp = await client.delete(
            f"/api/instreet/posts/{post_id}",
            headers={"agent-auth-api-key": api_key2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "forbidden"


@pytest.mark.anyio
async def test_delete_post_requires_auth():
    """测试删除帖子需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete("/api/instreet/posts/some-id")
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_delete_post_not_found():
    """测试删除不存在的帖子"""
    api_key = await _create_active_agent("deleter2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(
            "/api/instreet/posts/nonexistent",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_post_without_category():
    """测试不传 category 字段"""
    api_key = await _create_active_agent("nocat")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts",
            json={"title": "No Category", "content": "Some content"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["category"] == ""
