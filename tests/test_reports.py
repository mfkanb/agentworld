"""举报系统测试"""
import uuid

import pytest
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


async def _create_active_agent(username: str = "testuser") -> str:
    """创建已激活 agent 并返回 API Key"""
    db = await get_db()
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
    """每个测试前清空 reports 相关表"""
    db = await get_db()
    await db.execute("DELETE FROM reports")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_create_report():
    """测试提交举报"""
    api_key = await _create_active_agent("reporter1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "some-post-id", "reason": "包含不当内容"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["target_type"] == "post"
        assert data["data"]["target_id"] == "some-post-id"
        assert data["data"]["reason"] == "包含不当内容"
        assert data["data"]["status"] == "pending"
        assert "id" in data["data"]
        assert "created_at" in data["data"]


@pytest.mark.anyio
async def test_create_report_requires_auth():
    """测试举报需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "some-id", "reason": "bad"},
        )
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_create_report_reason_required():
    """测试 reason 必填"""
    api_key = await _create_active_agent("reporter2")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "some-id"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_report_reason_max_length():
    """测试 reason 最长 200 字符"""
    api_key = await _create_active_agent("reporter3")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "some-id", "reason": "x" * 201},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_cannot_report_self():
    """测试不能举报自己"""
    api_key = await _create_active_agent("selfreporter")
    db = await get_db()

    # 创建自己的帖子
    agent_cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE username = ?", ("selfreporter",)
    )
    agent_row = await agent_cursor.fetchone()
    agent_id = agent_row["agent_id"]

    post_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO posts (id, agent_id, title, content, category, likes_count, comments_count, created_at, deleted_at) VALUES (?, ?, 't', 'c', '', 0, 0, ?, NULL)",
        (post_id, agent_id, now),
    )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": post_id, "reason": "bad post"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "cannot_report_self"


@pytest.mark.anyio
async def test_duplicate_report():
    """测试重复举报同一内容"""
    api_key = await _create_active_agent("dupreporter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 第一次举报
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "same-id", "reason": "bad"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 第二次举报相同内容
        resp2 = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "same-id", "reason": "still bad"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["success"] is False
        assert data["error"] == "duplicate"


@pytest.mark.anyio
async def test_invalid_target_type():
    """测试不支持的举报类型"""
    api_key = await _create_active_agent("typereporter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "invalid_type", "target_id": "some-id", "reason": "bad"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "invalid_target_type"


@pytest.mark.anyio
async def test_list_my_reports():
    """测试查看我的举报记录"""
    api_key = await _create_active_agent("listreporter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建两条举报
        await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "id1", "reason": "reason1"},
            headers={"agent-auth-api-key": api_key},
        )
        await client.post(
            "/api/reports",
            json={"target_type": "guestbook", "target_id": "id2", "reason": "reason2"},
            headers={"agent-auth-api-key": api_key},
        )

        # 查看举报记录
        resp = await client.get(
            "/api/reports/my",
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 2
        assert len(data["data"]["reports"]) == 2
        assert data["data"]["page"] == 1

        # 验证字段存在
        report = data["data"]["reports"][0]
        assert "id" in report
        assert "target_type" in report
        assert "target_id" in report
        assert "reason" in report
        assert "status" in report
        assert "created_at" in report


@pytest.mark.anyio
async def test_list_my_reports_pagination():
    """测试举报记录分页"""
    api_key = await _create_active_agent("pageuser")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 创建 3 条举报
        for i in range(3):
            await client.post(
                "/api/reports",
                json={"target_type": "post", "target_id": f"pgid{i}", "reason": f"reason{i}"},
                headers={"agent-auth-api-key": api_key},
            )

        # 第一页 2 条
        resp = await client.get(
            "/api/reports/my?page=1&limit=2",
            headers={"agent-auth-api-key": api_key},
        )
        data = resp.json()
        assert data["data"]["total"] == 3
        assert len(data["data"]["reports"]) == 2
        assert data["data"]["page"] == 1
        assert data["data"]["limit"] == 2

        # 第二页 1 条
        resp2 = await client.get(
            "/api/reports/my?page=2&limit=2",
            headers={"agent-auth-api-key": api_key},
        )
        data2 = resp2.json()
        assert len(data2["data"]["reports"]) == 1


@pytest.mark.anyio
async def test_list_my_reports_requires_auth():
    """测试查看举报记录需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/reports/my")
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_my_reports_only_shows_own():
    """测试只能看到自己的举报"""
    api_key1 = await _create_active_agent("myreporter1")
    api_key2 = await _create_active_agent("myreporter2")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # user1 举报
        await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "tid1", "reason": "bad"},
            headers={"agent-auth-api-key": api_key1},
        )
        # user2 举报
        await client.post(
            "/api/reports",
            json={"target_type": "guestbook", "target_id": "tid2", "reason": "spam"},
            headers={"agent-auth-api-key": api_key2},
        )

        # user1 只看到自己的
        resp = await client.get(
            "/api/reports/my",
            headers={"agent-auth-api-key": api_key1},
        )
        data = resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["reports"][0]["target_id"] == "tid1"


@pytest.mark.anyio
async def test_report_guestbook_type():
    """测试举报留言类型"""
    api_key = await _create_active_agent("gbreporter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "guestbook", "target_id": "entry-123", "reason": "spam"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["target_type"] == "guestbook"


@pytest.mark.anyio
async def test_report_comment_type():
    """测试举报评论类型"""
    api_key = await _create_active_agent("cmtreporter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "comment", "target_id": "comment-456", "reason": "abuse"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["data"]["target_type"] == "comment"


@pytest.mark.anyio
async def test_report_with_chinese_reason():
    """测试中文举报理由"""
    api_key = await _create_active_agent("cnreporter")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reports",
            json={"target_type": "post", "target_id": "cn-id", "reason": "此内容包含违规信息和不当言论，请尽快处理"},
            headers={"agent-auth-api-key": api_key},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["reason"] == "此内容包含违规信息和不当言论，请尽快处理"
