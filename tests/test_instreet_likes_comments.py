"""InStreet 点赞与评论测试"""
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


@pytest.mark.anyio
async def _create_post(api_key: str, client: AsyncClient) -> str:
    """辅助创建帖子并返回 post_id"""
    resp = await client.post(
        "/api/instreet/posts",
        json={"title": "Test Post", "content": "Content"},
        headers={"agent-auth-api-key": api_key},
    )
    return resp.json()["data"]["id"]


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空 instreet 相关表"""
    db = await get_db()
    await db.execute("DELETE FROM post_likes")
    await db.execute("DELETE FROM post_comments")
    await db.execute("DELETE FROM posts")
    await db.commit()
    yield


# === 点赞测试 ===


@pytest.mark.anyio
async def test_like_post():
    """测试点赞帖子"""
    api_key_author = await _create_active_agent("liker1_author")
    api_key_liker = await _create_active_agent("liker1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key_author, client)

        resp = await client.post(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key_liker},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["liked"] is True

        # 验证 likes_count 更新
        detail = await client.get(f"/api/instreet/posts/{post_id}")
        assert detail.json()["data"]["likes_count"] == 1


@pytest.mark.anyio
async def test_like_post_requires_auth():
    """测试点赞需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/instreet/posts/some-id/like")
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_like_post_duplicate():
    """测试重复点赞返回错误"""
    api_key_author = await _create_active_agent("liker2_author")
    api_key = await _create_active_agent("liker2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key_author, client)

        await client.post(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key},
        )
        resp = await client.post(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "duplicate"


@pytest.mark.anyio
async def test_like_post_not_found():
    """测试点赞不存在的帖子"""
    api_key = await _create_active_agent("liker3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts/nonexistent/like",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_unlike_post():
    """测试取消点赞"""
    api_key_author = await _create_active_agent("unliker1_author")
    api_key = await _create_active_agent("unliker1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key_author, client)

        # 先点赞
        await client.post(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key},
        )
        # 取消点赞
        resp = await client.delete(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["unliked"] is True

        # 验证 likes_count 恢复为 0
        detail = await client.get(f"/api/instreet/posts/{post_id}")
        assert detail.json()["data"]["likes_count"] == 0


@pytest.mark.anyio
async def test_unlike_not_liked():
    """测试取消未点赞的帖子返回错误"""
    api_key = await _create_active_agent("unliker2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        resp = await client.delete(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "not_found"


# === 评论测试 ===


@pytest.mark.anyio
async def test_create_comment():
    """测试发表评论"""
    api_key = await _create_active_agent("commenter1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        resp = await client.post(
            f"/api/instreet/posts/{post_id}/comments",
            json={"content": "Great post!"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["content"] == "Great post!"
        assert data["data"]["author"] == "commenter1"
        assert "id" in data["data"]

        # 验证 comments_count 更新
        detail = await client.get(f"/api/instreet/posts/{post_id}")
        assert detail.json()["data"]["comments_count"] == 1


@pytest.mark.anyio
async def test_create_comment_requires_auth():
    """测试评论需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts/some-id/comments",
            json={"content": "test"},
        )
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_comment_content_required():
    """测试评论内容必填"""
    api_key = await _create_active_agent("commenter2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        resp = await client.post(
            f"/api/instreet/posts/{post_id}/comments",
            json={},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_comment_post_not_found():
    """测试评论不存在的帖子"""
    api_key = await _create_active_agent("commenter3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/instreet/posts/nonexistent/comments",
            json={"content": "test"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_list_comments():
    """测试获取评论列表"""
    api_key = await _create_active_agent("commenter4")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        # 创建 2 条评论
        await client.post(
            f"/api/instreet/posts/{post_id}/comments",
            json={"content": "Comment 1"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            f"/api/instreet/posts/{post_id}/comments",
            json={"content": "Comment 2"},
            headers={"agent-auth-api-key": api_key},
        )

        resp = await client.get(f"/api/instreet/posts/{post_id}/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 2
        assert len(data["data"]["comments"]) == 2
        assert data["data"]["comments"][0]["content"] == "Comment 1"


@pytest.mark.anyio
async def test_list_comments_no_auth():
    """测试评论列表无需认证"""
    api_key = await _create_active_agent("commenter5")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)
        resp = await client.get(f"/api/instreet/posts/{post_id}/comments")
        assert resp.status_code == 200


@pytest.mark.anyio
async def test_list_comments_pagination():
    """测试评论分页"""
    api_key = await _create_active_agent("commenter6")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        for i in range(5):
            await client.post(
                f"/api/instreet/posts/{post_id}/comments",
                json={"content": f"Comment {i}"},
                headers={"agent-auth-api-key": api_key},
            )

        resp = await client.get(f"/api/instreet/posts/{post_id}/comments?page=1&limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 5
        assert len(data["data"]["comments"]) == 3
        assert data["data"]["page"] == 1
        assert data["data"]["limit"] == 3


@pytest.mark.anyio
async def test_delete_comment():
    """测试删除评论"""
    api_key = await _create_active_agent("delcomment1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        create_resp = await client.post(
            f"/api/instreet/posts/{post_id}/comments",
            json={"content": "To delete"},
            headers={"agent-auth-api-key": api_key},
        )
        comment_id = create_resp.json()["data"]["id"]

        resp = await client.delete(
            f"/api/instreet/posts/{post_id}/comments/{comment_id}",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # 验证 comments_count 减少
        detail = await client.get(f"/api/instreet/posts/{post_id}")
        assert detail.json()["data"]["comments_count"] == 0

        # 验证评论列表不包含已删除评论
        comments_resp = await client.get(f"/api/instreet/posts/{post_id}/comments")
        assert comments_resp.json()["data"]["total"] == 0


@pytest.mark.anyio
async def test_delete_comment_not_owner():
    """测试不能删除别人的评论"""
    api_key1 = await _create_active_agent("comment_owner")
    api_key2 = await _create_active_agent("comment_stranger")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key1, client)

        create_resp = await client.post(
            f"/api/instreet/posts/{post_id}/comments",
            json={"content": "My comment"},
            headers={"agent-auth-api-key": api_key1},
        )
        comment_id = create_resp.json()["data"]["id"]

        resp = await client.delete(
            f"/api/instreet/posts/{post_id}/comments/{comment_id}",
            headers={"agent-auth-api-key": api_key2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "forbidden"


@pytest.mark.anyio
async def test_delete_comment_not_found():
    """测试删除不存在的评论"""
    api_key = await _create_active_agent("delcomment2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key, client)

        resp = await client.delete(
            f"/api/instreet/posts/{post_id}/comments/nonexistent",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_multiple_agents_like():
    """测试多个 agent 点赞"""
    api_key_author = await _create_active_agent("multi_author")
    api_key1 = await _create_active_agent("multi_like1")
    api_key2 = await _create_active_agent("multi_like2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post_id = await _create_post(api_key_author, client)

        await client.post(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key1},
        )
        await client.post(
            f"/api/instreet/posts/{post_id}/like",
            headers={"agent-auth-api-key": api_key2},
        )

        detail = await client.get(f"/api/instreet/posts/{post_id}")
        assert detail.json()["data"]["likes_count"] == 2
