"""Tests for US-401: Task can_claim field."""
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
    db = await get_db()
    await db.execute("DELETE FROM task_completions")
    await db.execute("DELETE FROM tasks")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


async def _create_active_agent(client: AsyncClient, username: str) -> dict:
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
async def test_can_claim_false_when_progress_zero(client):
    """can_claim is false when progress is 0."""
    headers = await _create_active_agent(client, "claimuser1")
    resp = await client.get("/api/tasks", headers=headers)
    tasks = resp.json()["data"]["tasks"]

    daily_checkin = next(t for t in tasks if t["id"] == "daily_checkin")
    assert daily_checkin["progress"] == 0
    assert daily_checkin["is_completed"] is False
    assert daily_checkin["can_claim"] is False


@pytest.mark.anyio
async def test_can_claim_true_when_progress_met(client):
    """can_claim is true when progress >= target_count and not completed."""
    headers = await _create_active_agent(client, "claimuser2")
    api_key = headers["agent-auth-api-key"]
    db = await get_db()

    # Complete profile (set nickname)
    await db.execute(
        "UPDATE agents SET nickname = 'TestNick' WHERE username = ?",
        ("claimuser2",),
    )
    await db.commit()

    resp = await client.get("/api/tasks", headers=headers)
    tasks = resp.json()["data"]["tasks"]

    profile_task = next(t for t in tasks if t["id"] == "beginner_complete_profile")
    assert profile_task["progress"] >= 1
    assert profile_task["is_completed"] is False
    assert profile_task["can_claim"] is True


@pytest.mark.anyio
async def test_can_claim_false_after_completion(client):
    """can_claim is false after task is completed."""
    headers = await _create_active_agent(client, "claimuser3")
    db = await get_db()

    # Complete profile
    await db.execute(
        "UPDATE agents SET nickname = 'Completed' WHERE username = ?",
        ("claimuser3",),
    )
    await db.commit()

    # Claim the reward
    resp = await client.post(
        "/api/tasks/beginner_complete_profile/complete",
        headers=headers,
    )
    assert resp.json()["success"] is True

    # Check can_claim is now false
    resp = await client.get("/api/tasks", headers=headers)
    tasks = resp.json()["data"]["tasks"]

    profile_task = next(t for t in tasks if t["id"] == "beginner_complete_profile")
    assert profile_task["is_completed"] is True
    assert profile_task["can_claim"] is False


@pytest.mark.anyio
async def test_can_claim_present_in_all_tasks(client):
    """All task objects have can_claim field."""
    headers = await _create_active_agent(client, "claimuser4")
    resp = await client.get("/api/tasks", headers=headers)
    tasks = resp.json()["data"]["tasks"]

    assert len(tasks) > 0
    for task in tasks:
        assert "can_claim" in task
        assert isinstance(task["can_claim"], bool)
