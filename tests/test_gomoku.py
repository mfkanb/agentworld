"""PlayLab 五子棋测试"""
import json

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


async def _create_and_start_gomoku() -> tuple[dict, dict, str]:
    """创建两个 Agent，创建五子棋房间并开始游戏，返回 (a1, a2, room_id)"""
    a1 = await _create_active_agent("gmk_host")
    a2 = await _create_active_agent("gmk_guest")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": a2["api_key"]})
        await ac.post(f"/api/playlab/rooms/{room_id}/start", headers={"agent-auth-api-key": a1["api_key"]})

    return a1, a2, room_id


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM game_states")
    await db.execute("DELETE FROM game_players")
    await db.execute("DELETE FROM game_rooms")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


@pytest.mark.anyio
async def test_gomoku_init_board_on_start():
    """测试开始五子棋游戏时初始化棋盘"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": a1["api_key"]})

    data = resp.json()
    assert data["success"] is True
    state = data["data"]
    assert state["game_type"] == "gomoku"
    assert state["status"] == "playing"
    assert state["board"] == [[0] * 15 for _ in range(15)]
    assert state["current_turn"] == 0
    assert state["last_move"] is None
    assert state["move_count"] == 0


@pytest.mark.anyio
async def test_gomoku_place_first_move():
    """测试五子棋第一手落子（player 0 → 黑）"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 7, "col": 7},
            headers={"agent-auth-api-key": a1["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["piece"] == 1  # 黑
    assert data["data"]["row"] == 7
    assert data["data"]["col"] == 7
    assert data["data"]["move_count"] == 1
    assert data["data"]["current_turn"] == 1  # 轮到白
    assert data["data"]["status"] == "playing"


@pytest.mark.anyio
async def test_gomoku_place_second_move():
    """测试五子棋第二手落子（player 1 → 白）"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方落子
        await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 7, "col": 7},
            headers={"agent-auth-api-key": a1["api_key"]},
        )
        # 白方落子
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 8, "col": 8},
            headers={"agent-auth-api-key": a2["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["piece"] == 2  # 白
    assert data["data"]["move_count"] == 2
    assert data["data"]["current_turn"] == 0  # 轮到黑


@pytest.mark.anyio
async def test_gomoku_not_your_turn():
    """测试不在自己回合落子"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 白方在黑方回合落子
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 7, "col": 7},
            headers={"agent-auth-api-key": a2["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_your_turn"


@pytest.mark.anyio
async def test_gomoku_position_occupied():
    """测试在已有棋子的位置落子"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方落子 (7,7)
        await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 7, "col": 7},
            headers={"agent-auth-api-key": a1["api_key"]},
        )
        # 白方尝试在 (7,7) 落子
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 7, "col": 7},
            headers={"agent-auth-api-key": a2["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "position_occupied"


@pytest.mark.anyio
async def test_gomoku_invalid_action():
    """测试不支持的操作类型"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "surrender", "row": 0, "col": 0},
            headers={"agent-auth-api-key": a1["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "invalid_action"


@pytest.mark.anyio
async def test_gomoku_game_not_playing():
    """测试游戏未开始时无法操作"""
    a1 = await _create_active_agent("gnp1")
    a2 = await _create_active_agent("gnp2")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "gomoku"}, headers={"agent-auth-api-key": a1["api_key"]})
        room_id = resp.json()["data"]["id"]

        # 游戏还在等待状态
        resp2 = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 0, "col": 0},
            headers={"agent-auth-api-key": a1["api_key"]},
        )

    data = resp2.json()
    assert data["success"] is False
    assert data["error"] == "game_not_playing"


@pytest.mark.anyio
async def test_gomoku_not_player():
    """测试非参与者无法操作"""
    a1, a2, room_id = await _create_and_start_gomoku()
    a3 = await _create_active_agent("gmk_outsider")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 0, "col": 0},
            headers={"agent-auth-api-key": a3["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_player"


@pytest.mark.anyio
async def test_gomoku_win_horizontal():
    """测试横向五连获胜"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方横向 (7,0)→(7,4)，白方落子不干扰
        for i in range(5):
            # 黑方落子
            resp_b = await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "place", "row": 7, "col": i},
                headers={"agent-auth-api-key": a1["api_key"]},
            )
            if i < 4:
                # 白方落子（不在同一行干扰）
                await ac.post(
                    f"/api/playlab/rooms/{room_id}/action",
                    json={"action": "place", "row": 8, "col": i},
                    headers={"agent-auth-api-key": a2["api_key"]},
                )

    data = resp_b.json()
    assert data["success"] is True
    assert data["data"]["status"] == "finished"
    assert data["data"]["winner_id"] == a1["agent_id"]


@pytest.mark.anyio
async def test_gomoku_win_vertical():
    """测试纵向五连获胜"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方纵向 (0,0)→(4,0)
        for i in range(5):
            resp_b = await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "place", "row": i, "col": 0},
                headers={"agent-auth-api-key": a1["api_key"]},
            )
            if i < 4:
                await ac.post(
                    f"/api/playlab/rooms/{room_id}/action",
                    json={"action": "place", "row": i, "col": 1},
                    headers={"agent-auth-api-key": a2["api_key"]},
                )

    data = resp_b.json()
    assert data["success"] is True
    assert data["data"]["status"] == "finished"
    assert data["data"]["winner_id"] == a1["agent_id"]


@pytest.mark.anyio
async def test_gomoku_win_diagonal():
    """测试对角线五连获胜"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方对角线 (0,0)→(4,4)
        for i in range(5):
            resp_b = await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "place", "row": i, "col": i},
                headers={"agent-auth-api-key": a1["api_key"]},
            )
            if i < 4:
                await ac.post(
                    f"/api/playlab/rooms/{room_id}/action",
                    json={"action": "place", "row": i, "col": 14},
                    headers={"agent-auth-api-key": a2["api_key"]},
                )

    data = resp_b.json()
    assert data["success"] is True
    assert data["data"]["status"] == "finished"
    assert data["data"]["winner_id"] == a1["agent_id"]


@pytest.mark.anyio
async def test_gomoku_win_anti_diagonal():
    """测试反对角线五连获胜"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方反对角线 (0,4)→(4,0)
        for i in range(5):
            resp_b = await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "place", "row": i, "col": 4 - i},
                headers={"agent-auth-api-key": a1["api_key"]},
            )
            if i < 4:
                await ac.post(
                    f"/api/playlab/rooms/{room_id}/action",
                    json={"action": "place", "row": i, "col": 14},
                    headers={"agent-auth-api-key": a2["api_key"]},
                )

    data = resp_b.json()
    assert data["success"] is True
    assert data["data"]["status"] == "finished"
    assert data["data"]["winner_id"] == a1["agent_id"]


@pytest.mark.anyio
async def test_gomoku_state_after_moves():
    """测试落子后查看游戏状态"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方落子
        await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 7, "col": 7},
            headers={"agent-auth-api-key": a1["api_key"]},
        )
        # 白方落子
        await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 0, "col": 0},
            headers={"agent-auth-api-key": a2["api_key"]},
        )

        # 查看状态
        resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": a1["api_key"]})

    data = resp.json()
    assert data["success"] is True
    state = data["data"]
    assert state["board"][7][7] == 1  # 黑
    assert state["board"][0][0] == 2  # 白
    assert state["current_turn"] == 0  # 轮到黑
    assert state["move_count"] == 2
    assert state["last_move"] == {"row": 0, "col": 0}


@pytest.mark.anyio
async def test_gomoku_cannot_move_after_finished():
    """测试游戏结束后无法继续落子"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 黑方横向获胜
        for i in range(5):
            await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "place", "row": 7, "col": i},
                headers={"agent-auth-api-key": a1["api_key"]},
            )
            if i < 4:
                await ac.post(
                    f"/api/playlab/rooms/{room_id}/action",
                    json={"action": "place", "row": 8, "col": i},
                    headers={"agent-auth-api-key": a2["api_key"]},
                )

        # 白方尝试再落子
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place", "row": 6, "col": 6},
            headers={"agent-auth-api-key": a2["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "game_not_playing"


@pytest.mark.anyio
async def test_gomoku_action_not_found():
    """测试对不存在的房间操作"""
    agent = await _create_active_agent("gmk_nf")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms/nonexistent/action",
            json={"action": "place", "row": 0, "col": 0},
            headers={"agent-auth-api-key": agent["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "not_found"


@pytest.mark.anyio
async def test_gomoku_missing_row_col():
    """测试缺少 row/col 参数"""
    a1, a2, room_id = await _create_and_start_gomoku()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "place"},
            headers={"agent-auth-api-key": a1["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "missing_params"
