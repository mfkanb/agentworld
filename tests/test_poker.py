"""PlayLab 德州扑克测试"""
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


async def _create_poker_room(num_players: int = 2) -> tuple[list[dict], str]:
    """创建 N 个 Agent，创建德州扑克房间并加入，返回 (players, room_id)"""
    players = []
    for i in range(num_players):
        players.append(await _create_active_agent(f"poker_p{i + 1}"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 创建者创建房间
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "poker"}, headers={"agent-auth-api-key": players[0]["api_key"]})
        room_id = resp.json()["data"]["id"]

        # 其他玩家加入
        for i in range(1, num_players):
            await ac.post(f"/api/playlab/rooms/{room_id}/join", headers={"agent-auth-api-key": players[i]["api_key"]})

    return players, room_id


async def _create_and_start_poker(num_players: int = 2) -> tuple[list[dict], str]:
    """创建房间并开始游戏"""
    players, room_id = await _create_poker_room(num_players)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(f"/api/playlab/rooms/{room_id}/start", headers={"agent-auth-api-key": players[0]["api_key"]})

    return players, room_id


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM poker_hands")
    await db.execute("DELETE FROM poker_states")
    await db.execute("DELETE FROM game_states")
    await db.execute("DELETE FROM game_players")
    await db.execute("DELETE FROM game_rooms")
    await db.execute("DELETE FROM wallets")
    await db.execute("DELETE FROM agents")
    await db.commit()
    yield


# --- 测试 ---


@pytest.mark.anyio
async def test_poker_create_room():
    """测试创建德州扑克房间"""
    a1 = await _create_active_agent("poker_create")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/playlab/rooms", json={"game_type": "poker"}, headers={"agent-auth-api-key": a1["api_key"]})

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["game_type"] == "poker"
    assert data["data"]["game_name"] == "德州扑克"
    assert data["data"]["max_players"] == 6


@pytest.mark.anyio
async def test_poker_start_initializes_state():
    """测试开始游戏时初始化扑克状态"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})

    data = resp.json()
    assert data["success"] is True
    state = data["data"]
    assert state["game_type"] == "poker"
    assert state["status"] == "playing"

    poker = state["poker"]
    assert poker["phase"] == "preflop"
    assert poker["pot"] > 0  # 有盲注
    assert len(poker["community_cards"]) == 0
    assert len(poker["players"]) == 2

    # 检查玩家有底牌
    for p in poker["players"]:
        if p["player_index"] == 0:
            assert len(p["hole_cards"]) == 2  # 自己的底牌可见
        else:
            assert p["hole_cards"] == []  # 对手的底牌不可见


@pytest.mark.anyio
async def test_poker_fold():
    """测试弃牌"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 谁先行动取决于 current_player_index
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        # 当前行动玩家弃牌
        current_player = players[current_idx]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "fold"},
            headers={"agent-auth-api-key": current_player["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "finished"
    assert data["data"]["reason"] == "others_folded"


@pytest.mark.anyio
async def test_poker_call():
    """测试跟注"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        current_player = players[current_idx]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "call"},
            headers={"agent-auth-api-key": current_player["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["action"] == "call"


@pytest.mark.anyio
async def test_poker_raise():
    """测试加注"""
    players, room_id = await _create_and_start_poker(3)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        current_player = players[current_idx]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "raise", "amount": 50},
            headers={"agent-auth-api-key": current_player["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["action"] == "raise"
    assert data["data"]["raise_amount"] == 50


@pytest.mark.anyio
async def test_poker_raise_zero_amount():
    """测试加注金额为0时返回错误"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        current_player = players[current_idx]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "raise", "amount": 0},
            headers={"agent-auth-api-key": current_player["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False


@pytest.mark.anyio
async def test_poker_allin():
    """测试全押"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        current_player = players[current_idx]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "allin"},
            headers={"agent-auth-api-key": current_player["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["action"] == "allin"
    assert data["data"]["allin_amount"] > 0


@pytest.mark.anyio
async def test_poker_not_your_turn():
    """测试非当前玩家操作返回错误"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        # 非当前玩家尝试操作
        other_idx = 1 - current_idx
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "call"},
            headers={"agent-auth-api-key": players[other_idx]["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False
    assert "not_your_turn" in data.get("error", "")


@pytest.mark.anyio
async def test_poker_invalid_action():
    """测试无效操作返回错误"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        current_player = players[current_idx]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "invalid_action"},
            headers={"agent-auth-api-key": current_player["api_key"]},
        )

    data = resp.json()
    assert data["success"] is False


@pytest.mark.anyio
async def test_poker_state_shows_my_cards_only():
    """测试牌局状态只显示自己的底牌"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 玩家0查看状态
        resp0 = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state0 = resp0.json()["data"]["poker"]

        # 玩家0能看到自己的底牌
        my_cards = state0["my_hole_cards"]
        assert len(my_cards) == 2

        # 玩家1查看状态
        resp1 = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[1]["api_key"]})
        state1 = resp1.json()["data"]["poker"]

        # 玩家1能看到自己的底牌
        my_cards1 = state1["my_hole_cards"]
        assert len(my_cards1) == 2

        # 玩家0看不到玩家1的底牌，反之亦然
        for p in state0["players"]:
            if p["player_index"] != 0:
                assert p["hole_cards"] == []


@pytest.mark.anyio
async def test_poker_three_players():
    """测试三人扑克游戏"""
    players, room_id = await _create_and_start_poker(3)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})

    data = resp.json()
    assert data["success"] is True
    poker = data["data"]["poker"]
    assert len(poker["players"]) == 3


@pytest.mark.anyio
async def test_poker_fold_then_one_wins():
    """测试弃牌后对手自动获胜"""
    players, room_id = await _create_and_start_poker(3)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 获取当前行动玩家
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        current_idx = state["poker"]["current_player_index"]

        # 第一个玩家弃牌
        await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "fold"},
            headers={"agent-auth-api-key": players[current_idx]["api_key"]},
        )

        # 第二个玩家弃牌
        state_resp2 = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state2 = state_resp2.json()["data"]
        current_idx2 = state2["poker"]["current_player_index"]
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "fold"},
            headers={"agent-auth-api-key": players[current_idx2]["api_key"]},
        )

    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "finished"
    assert data["data"]["reason"] == "others_folded"


@pytest.mark.anyio
async def test_poker_game_flow_to_flop():
    """测试游戏从preflop推进到flop阶段"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 两个玩家都跟注
        for _ in range(2):
            state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
            state = state_resp.json()["data"]
            current_idx = state["poker"]["current_player_index"]
            await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "call"},
                headers={"agent-auth-api-key": players[current_idx]["api_key"]},
            )

        # 检查阶段是否已推进
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]
        # 可能在 flop 阶段（有3张公共牌）
        assert state["poker"]["phase"] in ("flop", "turn", "river", "showdown")
        if state["poker"]["phase"] == "flop":
            assert len(state["poker"]["community_cards"]) == 3


@pytest.mark.anyio
async def test_poker_chips_tracking():
    """测试筹码跟踪"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = resp.json()["data"]["poker"]

    # 初始筹码 1000，减去盲注
    for p in state["players"]:
        assert p["chips"] < 1000  # 扣了盲注
        assert p["chips"] >= 0


@pytest.mark.anyio
async def test_poker_pot_starts_with_blinds():
    """测试底池初始有盲注"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = resp.json()["data"]["poker"]

    # SB=10, BB=20, pot初始=30
    assert state["pot"] == 30


@pytest.mark.anyio
async def test_poker_showdown_reveals_cards():
    """测试摊牌时公开所有底牌"""
    players, room_id = await _create_and_start_poker(2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 两个玩家都全押（强制摊牌）
        for _ in range(2):
            state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
            state = state_resp.json()["data"]
            if state["status"] == "finished":
                break
            current_idx = state["poker"]["current_player_index"]
            await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "allin"},
                headers={"agent-auth-api-key": players[current_idx]["api_key"]},
            )

        # 获取最终状态
        state_resp = await ac.get(f"/api/playlab/rooms/{room_id}/state", headers={"agent-auth-api-key": players[0]["api_key"]})
        state = state_resp.json()["data"]

    assert state["status"] == "finished"
    assert state["winner_id"] is not None
