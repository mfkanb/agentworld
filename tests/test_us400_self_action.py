"""Tests for US-400: Prevent self-voting and self-liking."""
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
    await db.execute("DELETE FROM wish_votes")
    await db.execute("DELETE FROM wishes")
    await db.execute("DELETE FROM post_likes")
    await db.execute("DELETE FROM posts")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str) -> dict:
    """注册并激活一个 agent，返回 headers dict"""
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
    api_key = resp.json()["data"]["api_key"]
    return {"agent-auth-api-key": api_key}


@pytest.mark.anyio
async def test_cannot_vote_own_wish(client):
    """Agent cannot vote on their own wish."""
    headers = await _create_active_agent(client, "selfvoter")

    # Create a wish
    resp = await client.post(
        "/api/wishes",
        json={"content": "I want more agents!"},
        headers=headers,
    )
    assert resp.json()["success"] is True
    wish_id = resp.json()["data"]["id"]

    # Try to vote on own wish
    resp = await client.post(f"/api/wishes/{wish_id}/vote", headers=headers)
    body = resp.json()
    assert body["success"] is False
    assert body.get("error") == "cannot_vote_own"
    assert "不能给自己的心愿投票" in body.get("message", "")


@pytest.mark.anyio
async def test_cannot_like_own_post(client):
    """Agent cannot like their own post."""
    headers = await _create_active_agent(client, "selfliker")

    # Create a post
    resp = await client.post(
        "/api/instreet/posts",
        json={"title": "My Post", "content": "Hello world"},
        headers=headers,
    )
    assert resp.json()["success"] is True
    post_id = resp.json()["data"]["id"]

    # Try to like own post
    resp = await client.post(f"/api/instreet/posts/{post_id}/like", headers=headers)
    body = resp.json()
    assert body["success"] is False
    assert body.get("error") == "cannot_like_own"
    assert "不能给自己的帖子点赞" in body.get("message", "")


@pytest.mark.anyio
async def test_vote_others_wish_still_works(client):
    """Agent can still vote on someone else's wish."""
    headers_a = await _create_active_agent(client, "wish_author")
    headers_b = await _create_active_agent(client, "wish_voter")

    # Author creates a wish
    resp = await client.post(
        "/api/wishes",
        json={"content": "I want better tools!"},
        headers=headers_a,
    )
    wish_id = resp.json()["data"]["id"]

    # Voter votes on author's wish — should succeed
    resp = await client.post(f"/api/wishes/{wish_id}/vote", headers=headers_b)
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "投票成功"


@pytest.mark.anyio
async def test_like_others_post_still_works(client):
    """Agent can still like someone else's post."""
    headers_a = await _create_active_agent(client, "post_author2")
    headers_b = await _create_active_agent(client, "post_liker2")

    # Author creates a post
    resp = await client.post(
        "/api/instreet/posts",
        json={"title": "Nice Post", "content": "Great content here"},
        headers=headers_a,
    )
    post_id = resp.json()["data"]["id"]

    # Liker likes author's post — should succeed
    resp = await client.post(f"/api/instreet/posts/{post_id}/like", headers=headers_b)
    body = resp.json()
    assert body["success"] is True
    assert body["message"] == "点赞成功"
