"""PlayLab 游戏房间系统测试"""
import pytest
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.services.database import get_db


# --- 辅助函数 ---


async def _create_active_agent(username: str = "player1") -> dict:
    """创建一个激活的 Agent 并返回 {agent_id, api_key, username}"""
    db = await get_db()
    import uuid
    import secrets

    agent_id = str(uuid.uuid4())
    api_key = "agent-world-" + secrets.token_hex(24)
    now = "2026-01-01T00:00:00+00:00"

    await db.execute(
        """INSERT INTO agents (agent_id, username, nickname, bio, avatar_url, api_key, is_active, verification_code, challenge_answer, challenge_expires_at, attempt_count, created_at)
           VALUES (?, ?, ?, '', '', ?, 1, '', '', '', 0, ?)""",
        (agent_id, username, username, api_key, now),
    )
    await db.commit()
    return {"agent_id": agent_id, "api_key": api_key, "username": username}


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM game_players")
    await db.execute("DELETE FROM game_rooms")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_create_room_gomoku():
    """测试创建五子棋房间"""
    agent = await _create_active_agent("creator1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "gomoku"},
            headers={"agent-auth-api-key": agent["api_key"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["game_type"] == "gomoku"
    assert data["data"]["status"] == "waiting"
    assert data["data"]["max_players"] == 2
    assert data["data"]["current_players"] == 1
    assert data["data"]["creator"]["username"] == "creator1"
    assert data["data"]["creator"]["player_index"] == 0


@pytest.mark.anyio
async def test_create_room_poker():
    """测试创建德州扑克房间"""
    agent = await _create_active_agent("poker_player")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "poker"},
            headers={"agent-auth-api-key": agent["api_key"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["game_type"] == "poker"
    assert data["data"]["max_players"] == 6


@pytest.mark.anyio
async def test_create_room_werewolf():
    """测试创建谁是卧底房间"""
    agent = await _create_active_agent("ww_player")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "werewolf"},
            headers={"agent-auth-api-key": agent["api_key"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["game_type"] == "werewolf"
    assert data["data"]["max_players"] == 8


@pytest.mark.anyio
async def test_create_room_invalid_type():
    """测试创建不支持的游戏类型"""
    agent = await _create_active_agent("badtype")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "chess"},
            headers={"agent-auth-api-key": agent["api_key"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "invalid_game_type"


@pytest.mark.anyio
async def test_create_room_requires_auth():
    """测试创建房间需要认证"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "gomoku"},
        )

    assert resp.status_code == 401


@pytest.mark.anyio
async def test_list_rooms():
    """测试获取等待中的房间列表"""
    a1 = await _create_active_agent("list_p1")
    a2 = await _create_active_agent("list_p2")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 创建两个房间
        await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        await ac.post("/api/playlab/rooms", json={"game_type": "poker"}, headers={"agent-auth-api-key": a2["api_key"]})

        # 获取列表（无需认证）
        resp = await ac.get("/api/playlab/rooms")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["total"] == 2
    assert len(data["data"]["rooms"]) == 2


@pytest.mark.anyio
async def test_list_rooms_pagination():
    """测试房间列表分页"""
    a1 = await _create_active_agent("page_p1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 创建3个房间
        for _ in range(3):
            await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})

        # 分页
        resp = await ac.get("/api/playlab/rooms", params={"page": 1, "limit": 2})
        data = resp.json()
        assert data["data"]["total"] == 3
        assert len(data["data"]["rooms"]) == 2

        resp2 = await ac.get("/api/playlab/rooms", params={"page": 2, "limit": 2})
        data2 = resp2.json()
        assert len(data2["data"]["rooms"]) == 1


@pytest.mark.anyio
async def test_join_room():
    """测试加入房间"""
    a1 = await _create_active_agent("host")
    a2 = await _create_active_agent("joiner")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 创建房间
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        # 另一个玩家加入
        resp2 = await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})

    assert resp2.status_code == 200
    data = resp2.json()
    assert data["success"] is True
    assert data["data"]["player_index"] == 1
    assert data["data"]["current_players"] == 2


@pytest.mark.anyio
async def test_join_room_already_joined():
    """测试重复加入房间"""
    a1 = await _create_active_agent("dup1")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        # 创建者再次尝试加入
        resp2 = await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a1["api_key"]})

    assert resp2.status_code == 200
    data = resp2.json()
    assert data["success"] is False
    assert data["error"] == "already_joined"


@pytest.mark.anyio
async def test_join_room_full():
    """测试加入已满的房间"""
    a1 = await _create_active_agent("full_host")
    a2 = await _create_active_agent("full_joiner")
    a3 = await _create_active_agent("full_reject")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        # a2 加入（2人房间满了）
        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})

        # a3 尝试加入
        resp3 = await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a3["api_key"]})

    assert resp3.status_code == 200
    data = resp3.json()
    assert data["success"] is False
    assert data["error"] == "room_full"


@pytest.mark.anyio
async def test_join_room_not_found():
    """测试加入不存在的房间"""
    agent = await _create_active_agent("nf_joiner")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms/nonexistent/join", headers={"agent-auth-api-key": agent["api_key"]})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_start_room():
    """测试开始游戏（创建者满员后开始）"""
    a1 = await _create_active_agent("start_h")
    a2 = await _create_active_agent("start_j")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        # 加入
        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})

        # 开始
        resp3 = await ac.post(f"/api/playlab/rooms/{room_id}/start", headers={"agent-auth-api-key": a1["api_key"]})

    assert resp3.status_code == 200
    data = resp3.json()
    assert data["success"] is True
    assert data["data"]["status"] == "playing"
    assert len(data["data"]["players"]) == 2


@pytest.mark.anyio
async def test_start_room_not_creator():
    """测试非创建者无法开始游戏"""
    a1 = await _create_active_agent("start_nch")
    a2 = await _create_active_agent("start_ncj")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})

        # 非创建者尝试开始
        resp3 = await ac.post(f"/api/playlab/rooms/{room_id}/start", headers={"agent-auth-api-key": a2["api_key"]})

    assert resp3.status_code == 200
    data = resp3.json()
    assert data["success"] is False
    assert data["error"] == "not_creator"


@pytest.mark.anyio
async def test_start_room_not_full():
    """测试房间未满时无法开始"""
    a1 = await _create_active_agent("start_nf_h")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        # 只有1人，2人房间未满
        resp2 = await ac.post(f"/api/playlab/rooms/{room_id}/start", headers={"agent-auth-api-key": a1["api_key"]})

    assert resp2.status_code == 200
    data = resp2.json()
    assert data["success"] is False
    assert data["error"] == "room_not_full"


@pytest.mark.anyio
async def test_get_room_state():
    """测试查看游戏状态"""
    a1 = await _create_active_agent("state_h")
    a2 = await _create_active_agent("state_j")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})

        # 参与者查看状态
        resp3 = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": a1["api_key"]})

    assert resp3.status_code == 200
    data = resp3.json()
    assert data["success"] is True
    assert data["data"]["room_id"] == room_id
    assert data["data"]["game_type"] == "gomoku"
    assert data["data"]["status"] == "waiting"
    assert len(data["data"]["players"]) == 2
    assert data["data"]["my_player_index"] == 0


@pytest.mark.anyio
async def test_get_room_state_not_player():
    """测试非参与者无法查看游戏状态"""
    a1 = await _create_active_agent("state_np_h")
    a2 = await _create_active_agent("state_np_j")
    a3 = await _create_active_agent("state_np_x")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})

        # 非参与者尝试查看
        resp3 = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": a3["api_key"]})

    assert resp3.status_code == 200
    data = resp3.json()
    assert data["success"] is False
    assert data["error"] == "not_player"


@pytest.mark.anyio
async def test_get_room_state_not_found():
    """测试查看不存在的房间状态"""
    agent = await _create_active_agent("state_nf")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/playlab/rooms/nonexistent/state", headers={"agent-auth-api-key": agent["api_key"]})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_cannot_join_playing_room():
    """测试不能加入已开始的房间"""
    a1 = await _create_active_agent("play_h")
    a2 = await _create_active_agent("play_j")
    a3 = await _create_active_agent("play_late")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})
        await ac.post(f"/api/playlab/rooms/{room_id}/start", headers={"agent-auth-api-key": a1["api_key"]})

        # 游戏开始后尝试加入
        resp3 = await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a3["api_key"]})

    assert resp3.status_code == 200
    data = resp3.json()
    assert data["success"] is False
    assert data["error"] == "room_not_waiting"
