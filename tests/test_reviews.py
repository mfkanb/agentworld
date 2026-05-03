"""US-013 虾评-技能评测系统测试"""
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
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM reviews")
    await db.execute("DELETE FROM favorites")
    await db.execute("DELETE FROM downloads")
    await db.execute("DELETE FROM skills")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str = "reviewer") -> tuple[str, str]:
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


def _auth_header(api_key: str) -> dict:
    return {"agent-auth-api-key": api_key}


async def _create_skill(client: AsyncClient, api_key: str, name: str = "test-skill") -> str:
    """创建技能并返回 skill_id"""
    resp = await client.post(
        "/api/skills",
        json={"name": name, "description": "A test skill", "category": "tools"},
        headers=_auth_header(api_key),
    )
    return resp.json()["data"]["id"]


async def _setup_author_and_reviewer(client: AsyncClient):
    """创建作者和评审者，返回 (author_key, reviewer_id, reviewer_key, skill_id)"""
    _, author_key = await _create_active_agent(client, "skill_author")
    reviewer_id, reviewer_key = await _create_active_agent(client, "skill_reviewer")
    skill_id = await _create_skill(client, author_key, "reviewed-skill")
    return author_key, reviewer_id, reviewer_key, skill_id


# --- POST /api/skills/{id}/comments ---


@pytest.mark.anyio
async def test_create_review_basic(client: AsyncClient):
    """基础评测 +1 虾米"""
    _, reviewer_id, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 4},
        headers=_auth_header(reviewer_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["rating"] == 4
    assert data["data"]["reward"] == 1

    # Check xiami
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM wallets WHERE agent_id = ?", (reviewer_id,))
    row = await cursor.fetchone()
    assert row["balance"] == 1


@pytest.mark.anyio
async def test_create_review_complete_with_dimensions(client: AsyncClient):
    """完整评测（含3维度）+3 虾米"""
    _, reviewer_id, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={
            "rating": 5,
            "content": "Great skill!",
            "functionality": 5,
            "effectiveness": 4,
            "scarcity": 3,
        },
        headers=_auth_header(reviewer_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward"] == 3

    # Check xiami
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM wallets WHERE agent_id = ?", (reviewer_id,))
    row = await cursor.fetchone()
    assert row["balance"] == 3


@pytest.mark.anyio
async def test_create_review_with_model_info(client: AsyncClient):
    """含模型信息额外 +1 虾米"""
    _, reviewer_id, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={
            "rating": 4,
            "model_info": "Claude 3.5 Sonnet",
            "functionality": 4,
            "effectiveness": 4,
            "scarcity": 4,
        },
        headers=_auth_header(reviewer_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward"] == 4  # 3 (complete) + 1 (model_info)

    # Check xiami
    db = await get_db()
    cursor = await db.execute("SELECT balance FROM wallets WHERE agent_id = ?", (reviewer_id,))
    row = await cursor.fetchone()
    assert row["balance"] == 4


@pytest.mark.anyio
async def test_create_review_basic_with_model_info(client: AsyncClient):
    """基础评测 + 模型信息 = +2 虾米"""
    _, reviewer_id, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 3, "model_info": "GPT-4"},
        headers=_auth_header(reviewer_key),
    )
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["reward"] == 2  # 1 (basic) + 1 (model_info)


@pytest.mark.anyio
async def test_create_review_updates_skill_rating(client: AsyncClient):
    """评测后更新技能总评分"""
    _, _, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 4},
        headers=_auth_header(reviewer_key),
    )

    db = await get_db()
    cursor = await db.execute("SELECT rating, rating_count FROM skills WHERE skill_id = ?", (skill_id,))
    row = await cursor.fetchone()
    assert row["rating"] == 4.0
    assert row["rating_count"] == 1


@pytest.mark.anyio
async def test_create_review_average_rating(client: AsyncClient):
    """多个评测计算平均分"""
    author_key, _, _, skill_id = await _setup_author_and_reviewer(client)

    # Reviewer 1: rating 5
    _, r1_key = await _create_active_agent(client, "rev1")
    await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 5},
        headers=_auth_header(r1_key),
    )

    # Reviewer 2: rating 3
    _, r2_key = await _create_active_agent(client, "rev2")
    await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 3},
        headers=_auth_header(r2_key),
    )

    db = await get_db()
    cursor = await db.execute("SELECT rating, rating_count FROM skills WHERE skill_id = ?", (skill_id,))
    row = await cursor.fetchone()
    assert row["rating"] == 4.0  # (5+3)/2
    assert row["rating_count"] == 2


@pytest.mark.anyio
async def test_create_review_requires_auth(client: AsyncClient):
    """评测需要 API Key"""
    resp = await client.post(f"/api/skills/{str(uuid.uuid4())}/comments", json={"rating": 4})
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_review_rating_required(client: AsyncClient):
    """rating 必填"""
    _, _, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={},
        headers=_auth_header(reviewer_key),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_review_rating_range(client: AsyncClient):
    """rating 只接受 1-5"""
    _, _, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 0},
        headers=_auth_header(reviewer_key),
    )
    assert resp.status_code == 422

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 6},
        headers=_auth_header(reviewer_key),
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_review_skill_not_found(client: AsyncClient):
    """评测不存在的技能"""
    _, _, reviewer_key, _ = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{str(uuid.uuid4())}/comments",
        json={"rating": 4},
        headers=_auth_header(reviewer_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_create_review_own_skill_forbidden(client: AsyncClient):
    """不能评测自己的技能"""
    author_key, _, _, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 5},
        headers=_auth_header(author_key),
    )
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "bad_request"


@pytest.mark.anyio
async def test_create_review_dimension_range(client: AsyncClient):
    """评测维度 1-5"""
    _, _, reviewer_key, skill_id = await _setup_author_and_reviewer(client)

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 4, "functionality": 0},
        headers=_auth_header(reviewer_key),
    )
    assert resp.status_code == 422

    resp = await client.post(
        f"/api/skills/{skill_id}/comments",
        json={"rating": 4, "effectiveness": 6},
        headers=_auth_header(reviewer_key),
    )
    assert resp.status_code == 422
