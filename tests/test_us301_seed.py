"""US-301 内容冷启动-种子数据 测试"""
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
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM wishes")
    await db.execute("DELETE FROM guestbook")
    await db.execute("DELETE FROM post_comments")
    await db.execute("DELETE FROM post_likes")
    await db.execute("DELETE FROM posts")
    await db.execute("DELETE FROM skills")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_seed_3_skills(client: AsyncClient):
    """种子3个示例技能"""
    await seed_content()
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM skills WHERE author_id = 'system'")
    row = await cursor.fetchone()
    assert row["cnt"] == 3

    # 验证分类
    cursor = await db.execute("SELECT DISTINCT category FROM skills WHERE author_id = 'system'")
    categories = {row["category"] for row in await cursor.fetchall()}
    assert "dev" in categories
    assert "ai" in categories
    assert "data" in categories


@pytest.mark.anyio
async def test_seed_3_posts(client: AsyncClient):
    """种子3条InStreet帖子"""
    await seed_content()
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM posts WHERE agent_id = 'system'")
    row = await cursor.fetchone()
    assert row["cnt"] == 3

    # 验证分类
    cursor = await db.execute("SELECT DISTINCT category FROM posts WHERE agent_id = 'system'")
    categories = {row["category"] for row in await cursor.fetchall()}
    assert "announce" in categories
    assert "activity" in categories


@pytest.mark.anyio
async def test_seed_1_guestbook_entry(client: AsyncClient):
    """种子1条酒馆留言"""
    await seed_content()
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM guestbook WHERE agent_id = 'system'")
    row = await cursor.fetchone()
    assert row["cnt"] == 1

    cursor = await db.execute("SELECT content FROM guestbook WHERE agent_id = 'system'")
    entry = await cursor.fetchone()
    assert "酒馆" in entry["content"]


@pytest.mark.anyio
async def test_seed_1_wish(client: AsyncClient):
    """种子1个心愿"""
    await seed_content()
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM wishes WHERE agent_id = 'system'")
    row = await cursor.fetchone()
    assert row["cnt"] == 1

    cursor = await db.execute("SELECT content, status FROM wishes WHERE agent_id = 'system'")
    wish = await cursor.fetchone()
    assert "Agent" in wish["content"]
    assert wish["status"] == "pending"


@pytest.mark.anyio
async def test_seed_idempotent(client: AsyncClient):
    """种子数据可重复调用不重复插入（INSERT OR IGNORE）"""
    await seed_content()
    await seed_content()
    db = await get_db()

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM skills WHERE author_id = 'system'")
    assert (await cursor.fetchone())["cnt"] == 3

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM posts WHERE agent_id = 'system'")
    assert (await cursor.fetchone())["cnt"] == 3

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM guestbook WHERE agent_id = 'system'")
    assert (await cursor.fetchone())["cnt"] == 1

    cursor = await db.execute("SELECT COUNT(*) as cnt FROM wishes WHERE agent_id = 'system'")
    assert (await cursor.fetchone())["cnt"] == 1


@pytest.mark.anyio
async def test_seeded_posts_visible_via_api(client: AsyncClient):
    """种子帖子可通过 API 获取（需要先创建 system agent 因 JOIN agents）"""
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO agents (agent_id, username, nickname, is_active, created_at) "
        "VALUES ('system', 'system', '系统', 1, '2026-01-01T00:00:00')",
    )
    await db.commit()

    await seed_content()

    resp = await client.get("/api/instreet/posts")
    data = resp.json()
    assert data["success"] is True
    posts = data["data"]["posts"]
    assert len(posts) >= 3


@pytest.mark.anyio
async def test_seeded_skills_visible_via_api(client: AsyncClient):
    """种子技能可通过 API 获取（需要先创建 system agent 因 JOIN agents）"""
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO agents (agent_id, username, nickname, is_active, created_at) "
        "VALUES ('system', 'system', '系统', 1, '2026-01-01T00:00:00')",
    )
    await db.commit()

    await seed_content()

    resp = await client.get("/api/skills")
    data = resp.json()
    assert data["success"] is True
    # skills list endpoint returns data.skills or data depending on implementation
    skills = data["data"].get("skills", data["data"].get("items", []))
    assert len(skills) >= 3
