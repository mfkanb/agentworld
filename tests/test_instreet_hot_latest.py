"""InStreet 浏览热门与最新测试"""
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
async def test_hot_posts_sorted_by_likes():
    """测试热门帖子按点赞数倒序"""
    api_key = await _create_active_agent("hotuser1")
    db = await get_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建 3 篇帖子
        r1 = await client.post("/api/instreet/posts", json={"title": "Post A", "content": "c"}, headers={"agent-auth-api-key": api_key})
        r2 = await client.post("/api/instreet/posts", json={"title": "Post B", "content": "c"}, headers={"agent-auth-api-key": api_key})
        r3 = await client.post("/api/instreet/posts", json={"title": "Post C", "content": "c"}, headers={"agent-auth-api-key": api_key})
        id_a = r1.json()["data"]["id"]
        id_b = r2.json()["data"]["id"]
        id_c = r3.json()["data"]["id"]

        # 手动设置 likes_count
        await db.execute("UPDATE posts SET likes_count = 5 WHERE id = ?", (id_a,))
        await db.execute("UPDATE posts SET likes_count = 20 WHERE id = ?", (id_b,))
        await db.execute("UPDATE posts SET likes_count = 10 WHERE id = ?", (id_c,))
        await db.commit()

        resp = await client.get("/api/instreet/posts/hot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 3
        posts = data["data"]["posts"]
        assert posts[0]["title"] == "Post B"  # 20 likes
        assert posts[1]["title"] == "Post C"  # 10 likes
        assert posts[2]["title"] == "Post A"  # 5 likes


@pytest.mark.anyio
async def test_hot_posts_pagination():
    """测试热门帖子分页"""
    api_key = await _create_active_agent("hotpage")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(5):
            await client.post("/api/instreet/posts", json={"title": f"P{i}", "content": "c"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/hot?page=1&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["posts"]) == 2
        assert data["data"]["total"] == 5
        assert data["data"]["page"] == 1
        assert data["data"]["limit"] == 2


@pytest.mark.anyio
async def test_hot_posts_category_filter():
    """测试热门帖子按分类筛选"""
    api_key = await _create_active_agent("hotcat")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/instreet/posts", json={"title": "Tech Post", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "Chat Post", "content": "c", "category": "chat"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/hot?category=tech")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["posts"][0]["title"] == "Tech Post"


@pytest.mark.anyio
async def test_hot_posts_no_deleted():
    """测试热门帖子不包含已删除的帖子"""
    api_key = await _create_active_agent("hotdel")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/instreet/posts", json={"title": "Keep", "content": "c"}, headers={"agent-auth-api-key": api_key})
        r2 = await client.post("/api/instreet/posts", json={"title": "Delete", "content": "c"}, headers={"agent-auth-api-key": api_key})

        await client.delete(f"/api/instreet/posts/{r2.json()['data']['id']}", headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/hot")
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["posts"][0]["title"] == "Keep"


@pytest.mark.anyio
async def test_latest_posts_sorted_by_time():
    """测试最新帖子按时间倒序"""
    api_key = await _create_active_agent("lateuser1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/instreet/posts", json={"title": "First", "content": "c"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "Second", "content": "c"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "Third", "content": "c"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 3
        posts = data["data"]["posts"]
        assert posts[0]["title"] == "Third"
        assert posts[1]["title"] == "Second"
        assert posts[2]["title"] == "First"


@pytest.mark.anyio
async def test_latest_posts_pagination():
    """测试最新帖子分页"""
    api_key = await _create_active_agent("latepage")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for i in range(4):
            await client.post("/api/instreet/posts", json={"title": f"P{i}", "content": "c"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/latest?page=2&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["posts"]) == 2
        assert data["data"]["total"] == 4
        assert data["data"]["page"] == 2


@pytest.mark.anyio
async def test_latest_posts_category_filter():
    """测试最新帖子按分类筛选"""
    api_key = await _create_active_agent("latecat")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/instreet/posts", json={"title": "Tech", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "Life", "content": "c", "category": "life"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "Tech2", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/latest?category=tech")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 2
        assert all(p["category"] == "tech" for p in data["data"]["posts"])


@pytest.mark.anyio
async def test_latest_posts_no_deleted():
    """测试最新帖子不包含已删除的帖子"""
    api_key = await _create_active_agent("latedel")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/instreet/posts", json={"title": "Keep", "content": "c"}, headers={"agent-auth-api-key": api_key})
        r2 = await client.post("/api/instreet/posts", json={"title": "Delete", "content": "c"}, headers={"agent-auth-api-key": api_key})

        await client.delete(f"/api/instreet/posts/{r2.json()['data']['id']}", headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/posts/latest")
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["posts"][0]["title"] == "Keep"


@pytest.mark.anyio
async def test_post_item_fields():
    """测试帖子列表每项包含正确的字段"""
    api_key = await _create_active_agent("fieldcheck")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/instreet/posts", json={"title": "Field Test", "content": "c"}, headers={"agent-auth-api-key": api_key})

        for endpoint in ["/api/instreet/posts/hot", "/api/instreet/posts/latest"]:
            resp = await client.get(endpoint)
            post = resp.json()["data"]["posts"][0]
            assert "id" in post
            assert "title" in post
            assert "likes_count" in post
            assert "comments_count" in post
            assert "created_at" in post
            assert "author" in post
            assert "nickname" in post["author"]


@pytest.mark.anyio
async def test_categories_list():
    """测试分类列表"""
    api_key = await _create_active_agent("catuser")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/instreet/posts", json={"title": "T1", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "T2", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "T3", "content": "c", "category": "chat"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        cats = data["data"]["categories"]
        cat_map = {c["name"]: c["post_count"] for c in cats}
        assert cat_map["tech"] == 2
        assert cat_map["chat"] == 1


@pytest.mark.anyio
async def test_categories_empty_category():
    """测试空 category 字段归入 uncategorized"""
    api_key = await _create_active_agent("nocatuser")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/instreet/posts", json={"title": "No Cat", "content": "c"}, headers={"agent-auth-api-key": api_key})
        await client.post("/api/instreet/posts", json={"title": "With Cat", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/categories")
        cats = resp.json()["data"]["categories"]
        cat_map = {c["name"]: c["post_count"] for c in cats}
        assert cat_map["uncategorized"] == 1
        assert cat_map["tech"] == 1


@pytest.mark.anyio
async def test_categories_exclude_deleted():
    """测试分类列表排除已删除帖子"""
    api_key = await _create_active_agent("catdel")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/instreet/posts", json={"title": "Keep", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})
        r2 = await client.post("/api/instreet/posts", json={"title": "Delete", "content": "c", "category": "tech"}, headers={"agent-auth-api-key": api_key})

        await client.delete(f"/api/instreet/posts/{r2.json()['data']['id']}", headers={"agent-auth-api-key": api_key})

        resp = await client.get("/api/instreet/categories")
        cats = resp.json()["data"]["categories"]
        cat_map = {c["name"]: c["post_count"] for c in cats}
        assert cat_map["tech"] == 1


@pytest.mark.anyio
async def test_hot_posts_empty():
    """测试热门帖子为空"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/instreet/posts/hot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["posts"] == []


@pytest.mark.anyio
async def test_latest_posts_empty():
    """测试最新帖子为空"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/instreet/posts/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0
        assert data["data"]["posts"] == []
