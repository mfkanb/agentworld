"""Tests for US-402: Expand InStreet seed content."""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db
from src.services.seed_content import seed_content


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
    db = await get_db()
    await db.execute("DELETE FROM posts")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_seed_content_total_posts():
    """Seed content has 15+ posts total."""
    await seed_content()
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM posts")
    count = (await cursor.fetchone())["cnt"]
    assert count >= 15


@pytest.mark.anyio
async def test_seed_content_category_coverage():
    """Seed content covers all 5 categories."""
    await seed_content()
    db = await get_db()
    cursor = await db.execute("SELECT DISTINCT category FROM posts")
    categories = {row["category"] for row in await cursor.fetchall()}
    for cat in ["tech", "discuss", "share", "activity", "ask"]:
        assert cat in categories, f"Missing category: {cat}"


@pytest.mark.anyio
async def test_seed_posts_use_system_agent():
    """All seed posts use 'system' as agent_id."""
    await seed_content()
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM posts WHERE agent_id != 'system'"
    )
    count = (await cursor.fetchone())["cnt"]
    assert count == 0


@pytest.mark.anyio
async def test_seed_posts_insert_or_ignore():
    """Running seed twice doesn't duplicate posts."""
    await seed_content()
    await seed_content()
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM posts")
    count = (await cursor.fetchone())["cnt"]
    assert count >= 15
    # Verify no duplicates by checking IDs
    cursor = await db.execute("SELECT COUNT(DISTINCT id) as cnt FROM posts")
    distinct = (await cursor.fetchone())["cnt"]
    assert distinct == count


@pytest.mark.anyio
async def test_seed_posts_have_realistic_likes():
    """Some seed posts have non-zero likes_count."""
    await seed_content()
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM posts WHERE likes_count > 0"
    )
    count = (await cursor.fetchone())["cnt"]
    assert count >= 5, "At least 5 posts should have initial likes"


@pytest.mark.anyio
async def test_seed_posts_visible_in_api(client):
    """Seed posts are visible via GET /api/instreet/posts."""
    await seed_content()
    resp = await client.get("/api/instreet/posts?limit=50")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] >= 15
