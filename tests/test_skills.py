"""US-010 虾评-技能列表与详情测试"""
import uuid
from datetime import datetime, timezone

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
async def _clean_skills():
    """每个测试前清空 skills 表"""
    db = await get_db()
    await db.execute("DELETE FROM skills")
    await db.commit()
    yield


async def _insert_skill(
    name: str = "test-skill",
    author_id: str = "",
    category: str = "",
    downloads: int = 0,
    rating: float = 0.0,
    rating_count: int = 0,
    deleted_at: str | None = None,
) -> str:
    """直接插入一条技能记录，返回 skill_id"""
    db = await get_db()
    skill_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO skills "
        "(skill_id, author_id, name, description, category, version, status, "
        "downloads, rating, rating_count, created_at, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, '1.0', 'published', ?, ?, ?, ?, ?)",
        (skill_id, author_id, name, f"Description of {name}", category,
         downloads, rating, rating_count, now, deleted_at),
    )
    await db.commit()
    return skill_id


async def _create_active_agent(client: AsyncClient, username: str = "skillbot") -> tuple[str, str]:
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
    return row["agent_id"], resp.json()["data"]["api_key"]


@pytest.mark.anyio
async def test_list_skills_empty(client: AsyncClient):
    """空列表返回空数组"""
    resp = await client.get("/api/skills")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["items"] == []
    assert data["data"]["total"] == 0


@pytest.mark.anyio
async def test_list_skills_with_data(client: AsyncClient):
    """有数据时返回技能列表"""
    await _insert_skill("python-tool")
    resp = await client.get("/api/skills")
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 1
    item = data["data"]["items"][0]
    assert item["name"] == "python-tool"
    assert "id" in item
    assert "description" in item
    assert "category" in item
    assert "downloads" in item
    assert "rating" in item
    assert "created_at" in item
    assert "author" in item


@pytest.mark.anyio
async def test_list_skills_pagination(client: AsyncClient):
    """分页：默认 limit=20，page 可指定"""
    for i in range(25):
        await _insert_skill(f"skill-{i:03d}")
    # 第一页
    resp = await client.get("/api/skills", params={"page": 1, "limit": 10})
    data = resp.json()
    assert data["data"]["total"] == 25
    assert len(data["data"]["items"]) == 10
    assert data["data"]["page"] == 1
    assert data["data"]["limit"] == 10

    # 第三页
    resp = await client.get("/api/skills", params={"page": 3, "limit": 10})
    data = resp.json()
    assert len(data["data"]["items"]) == 5


@pytest.mark.anyio
async def test_list_skills_search(client: AsyncClient):
    """搜索关键词"""
    await _insert_skill("web-scraper", category="data")
    await _insert_skill("image-tool", category="media")
    resp = await client.get("/api/skills", params={"search": "web"})
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["name"] == "web-scraper"


@pytest.mark.anyio
async def test_list_skills_category_filter(client: AsyncClient):
    """分类筛选"""
    await _insert_skill("web-scraper", category="data")
    await _insert_skill("image-tool", category="media")
    resp = await client.get("/api/skills", params={"category": "data"})
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["name"] == "web-scraper"


@pytest.mark.anyio
async def test_list_skills_sort_downloads(client: AsyncClient):
    """按下载量排序"""
    await _insert_skill("low-dl", downloads=5)
    await _insert_skill("high-dl", downloads=100)
    resp = await client.get("/api/skills", params={"sort": "downloads"})
    data = resp.json()
    assert data["data"]["items"][0]["name"] == "high-dl"
    assert data["data"]["items"][1]["name"] == "low-dl"


@pytest.mark.anyio
async def test_list_skills_sort_rating(client: AsyncClient):
    """按评分排序"""
    await _insert_skill("low-rate", rating=2.0)
    await _insert_skill("high-rate", rating=4.8)
    resp = await client.get("/api/skills", params={"sort": "rating"})
    data = resp.json()
    assert data["data"]["items"][0]["name"] == "high-rate"


@pytest.mark.anyio
async def test_list_skills_excludes_deleted(client: AsyncClient):
    """软删除的技能不在列表中"""
    await _insert_skill("active-skill")
    now = datetime.now(timezone.utc).isoformat()
    await _insert_skill("deleted-skill", deleted_at=now)
    resp = await client.get("/api/skills")
    data = resp.json()
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["name"] == "active-skill"


@pytest.mark.anyio
async def test_get_skill_detail(client: AsyncClient):
    """技能详情返回完整信息"""
    agent_id, _ = await _create_active_agent(client, "detailauthor")
    skill_id = await _insert_skill("detail-skill", author_id=agent_id, category="tools")
    resp = await client.get(f"/api/skills/{skill_id}")
    data = resp.json()
    assert data["success"] is True
    d = data["data"]
    assert d["id"] == skill_id
    assert d["name"] == "detail-skill"
    assert d["category"] == "tools"
    assert d["author"] == "detailauthor"
    assert "version" in d
    assert "status" in d
    assert "created_at" in d


@pytest.mark.anyio
async def test_get_skill_not_found(client: AsyncClient):
    """技能不存在返回 error"""
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/skills/{fake_id}")
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_get_categories(client: AsyncClient):
    """分类列表返回分类及技能数"""
    await _insert_skill("s1", category="data")
    await _insert_skill("s2", category="data")
    await _insert_skill("s3", category="media")
    resp = await client.get("/api/categories")
    data = resp.json()
    assert data["success"] is True
    items = data["data"]["items"]
    cat_map = {i["name"]: i["skill_count"] for i in items}
    assert cat_map["data"] == 2
    assert cat_map["media"] == 1


@pytest.mark.anyio
async def test_list_skills_author_join(client: AsyncClient):
    """列表中 author 字段来自 JOIN agents 表"""
    agent_id, _ = await _create_active_agent(client, "joinauthor")
    await _insert_skill("join-skill", author_id=agent_id)
    resp = await client.get("/api/skills")
    data = resp.json()
    assert data["data"]["items"][0]["author"] == "joinauthor"
