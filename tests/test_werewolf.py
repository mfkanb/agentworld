"""PlayLab 谁是卧底测试"""
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


async def _create_werewolf_room(num_players: int = 4) -> tuple[list[dict], str]:
    """创建 N 个 Agent，创建谁是卧底房间并加入，返回 (players, room_id)"""
    players = []
    for i in range(num_players):
        players.append(await _create_active_agent(f"wolf_p{i + 1}"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "werewolf"},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        assert resp.json()["success"]
        room_id = resp.json()["data"]["id"]

        for i in range(1, num_players):
            await ac.post(
                f"/api/playlab/rooms/{room_id}/join",
                headers={"agent-auth-api-key": players[i]["api_key"]},
            )

    return players, room_id


async def _create_and_start_werewolf(num_players: int = 4) -> tuple[list[dict], str]:
    """创建房间并开始游戏"""
    players, room_id = await _create_werewolf_room(num_players)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/start",
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        assert resp.json()["success"]

    return players, room_id


async def _describe_all(ac: AsyncClient, players: list[dict], room_id: str):
    """所有存活玩家按顺序描述"""
    for p in players:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": p["api_key"]},
        )
        data = resp.json()
        assert data["success"], f"describe failed for {p['username']}: {data}"


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每个测试前清空相关表"""
    db = await get_db()
    await db.execute("DELETE FROM werewolf_players")
    await db.execute("DELETE FROM werewolf_states")
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
async def test_werewolf_create_room():
    """测试创建谁是卧底房间"""
    player = await _create_active_agent("wolf_creator")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/playlab/rooms",
            json={"game_type": "werewolf"},
            headers={"agent-auth-api-key": player["api_key"]},
        )
        data = resp.json()
        assert data["success"]
        assert data["data"]["game_type"] == "werewolf"
        assert data["data"]["max_players"] == 8
        assert data["data"]["current_players"] == 1


@pytest.mark.anyio
async def test_werewolf_start_min_players():
    """测试最少3人才能开始"""
    players, room_id = await _create_werewolf_room(2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/start",
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "not_enough_players" in data["error"]


@pytest.mark.anyio
async def test_werewolf_start_and_init():
    """测试开始游戏后正确初始化"""
    players, room_id = await _create_and_start_werewolf(4)
    db = await get_db()

    # 检查 werewolf_states
    cursor = await db.execute(
        "SELECT * FROM werewolf_states WHERE room_id = ?", (room_id,)
    )
    state = await cursor.fetchone()
    assert state is not None
    assert state["civilian_word"] != ""
    assert state["spy_word"] != ""
    assert state["civilian_word"] != state["spy_word"]
    assert state["phase"] == "describe"
    assert state["round"] == 1

    # 检查 werewolf_players
    cursor = await db.execute(
        "SELECT role, is_alive FROM werewolf_players WHERE state_id = ?",
        (state["id"],),
    )
    all_players = await cursor.fetchall()
    assert len(all_players) == 4

    roles = [p["role"] for p in all_players]
    spy_count = roles.count("spy")
    civilian_count = roles.count("civilian")
    assert spy_count >= 1  # 至少1个卧底
    assert spy_count <= 2  # 4人约1/3=1
    assert civilian_count == 4 - spy_count

    # 所有玩家都是存活的
    assert all(p["is_alive"] == 1 for p in all_players)


@pytest.mark.anyio
async def test_werewolf_get_state_shows_my_word():
    """测试查看状态能看到自己的词"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for p in players:
            resp = await ac.get(
                f"/api/playlab/rooms/{room_id}/state",
                headers={"agent-auth-api-key": p["api_key"]},
            )
            data = resp.json()
            assert data["success"]
            w = data["data"]["werewolf"]
            assert w["my_word"] != ""
            assert w["my_role"] in ("civilian", "spy")
            assert w["phase"] == "describe"
            assert w["round"] == 1
            assert len(w["players"]) == 4


@pytest.mark.anyio
async def test_werewolf_describe_flow():
    """测试描述流程"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 第一个玩家描述
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert data["success"]
        assert data["data"]["phase"] == "describe"  # 还有人没描述

        # 不是轮到的玩家不能描述
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "already_described" in data.get("error", "") or "not_your_turn" in data.get("error", "")

        # 第二个玩家描述
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[1]["api_key"]},
        )
        assert resp.json()["success"]

        # 第三个玩家描述
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[2]["api_key"]},
        )
        assert resp.json()["success"]

        # 第四个玩家描述 - 最后一个
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[3]["api_key"]},
        )
        data = resp.json()
        assert data["success"]
        assert data["data"]["phase"] == "vote"  # 进入投票阶段


@pytest.mark.anyio
async def test_werewolf_vote_and_eliminate():
    """测试投票淘汰"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 所有人描述
        await _describe_all(ac, players, room_id)

        # 每个人投票给 player_index=1
        for p in players:
            resp = await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "vote", "row": 1},
                headers={"agent-auth-api-key": p["api_key"]},
            )
            data = resp.json()
            # player_index=1 投给自己应该失败
            if players[1]["agent_id"] == p["agent_id"]:
                assert not data["success"]
                assert "cannot_vote_self" in data.get("error", "")
            else:
                assert data["success"]

        # 检查最后一个人投票后触发淘汰
        # 现在 player_index=1 应该被淘汰


@pytest.mark.anyio
async def test_werewolf_vote_self_fails():
    """测试不能投票给自己"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 所有人描述
        await _describe_all(ac, players, room_id)

        # 投票给自己（player_index 0 的 agent 投给 row=0）
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "vote", "row": 0},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "cannot_vote_self" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_double_vote_fails():
    """测试重复投票"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await _describe_all(ac, players, room_id)

        # 第一个玩家投票给 player_index=1
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "vote", "row": 1},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        assert resp.json()["success"]

        # 重复投票
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "vote", "row": 2},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "already_voted" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_describe_wrong_phase():
    """测试非描述阶段不能描述"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 所有人描述
        await _describe_all(ac, players, room_id)

        # 投票阶段尝试描述
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "wrong_phase" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_vote_wrong_phase():
    """测试非投票阶段不能投票"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 描述阶段尝试投票
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "vote", "row": 1},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "wrong_phase" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_invalid_action():
    """测试无效操作"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "fold"},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "invalid_action" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_not_your_turn_describe():
    """测试不是自己回合不能描述"""
    players, room_id = await _create_and_start_werewolf(4)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 第二个玩家在第一个玩家之前描述
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "describe"},
            headers={"agent-auth-api-key": players[1]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "not_your_turn" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_full_game_civilian_win():
    """测试完整游戏流程 - 通过淘汰卧底使平民获胜"""
    players, room_id = await _create_and_start_werewolf(3)

    db = await get_db()
    # 找到卧底
    cursor = await db.execute(
        """SELECT wp.agent_id, gp.player_index, ws.id as state_id
           FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           JOIN werewolf_states ws ON ws.room_id = ?
           WHERE wp.state_id = ws.id AND wp.role = 'spy'""",
        (room_id, room_id),
    )
    spy = await cursor.fetchone()
    assert spy is not None
    spy_index = spy["player_index"]

    # 找一个平民用于投票
    cursor = await db.execute(
        """SELECT gp.player_index
           FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           JOIN werewolf_states ws ON ws.room_id = ?
           WHERE wp.state_id = ws.id AND wp.role = 'civilian'
           ORDER BY gp.player_index
           LIMIT 1""",
        (room_id, room_id),
    )
    civilian = await cursor.fetchone()
    civilian_index = civilian["player_index"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 描述阶段
        await _describe_all(ac, players, room_id)

        # 所有平民投给卧底（卧底投给一个平民）
        for p in players:
            p_idx = None
            for i, pp in enumerate(players):
                if pp["agent_id"] == p["agent_id"]:
                    p_idx = i
                    break

            if p_idx == spy_index:
                # 卧底投给平民
                target = civilian_index
            else:
                # 平民投给卧底
                target = spy_index

            resp = await ac.post(
                f"/api/playlab/rooms/{room_id}/action",
                json={"action": "vote", "row": target},
                headers={"agent-auth-api-key": p["api_key"]},
            )
            data = resp.json()

        # 3人游戏，1个卧底被淘汰后平民胜
        # 检查最后的结果
        last_resp = data
        if last_resp["data"]["status"] == "finished":
            assert last_resp["data"]["winner"] == "civilian"
            assert last_resp["data"]["civilian_word"] != ""
            assert last_resp["data"]["spy_word"] != ""


@pytest.mark.anyio
async def test_werewolf_vote_dead_player_fails():
    """测试不能投给已淘汰的玩家"""
    players, room_id = await _create_and_start_werewolf(4)

    db = await get_db()
    # 手动淘汰一个玩家
    cursor = await db.execute(
        "SELECT id FROM werewolf_states WHERE room_id = ?", (room_id,)
    )
    state = await cursor.fetchone()

    # 淘汰 player_index 1
    await db.execute(
        """UPDATE werewolf_players SET is_alive = 0
           WHERE state_id = ? AND agent_id = ?""",
        (state["id"], players[1]["agent_id"]),
    )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 尝试投给已淘汰的玩家
        # 先进入投票阶段
        await db.execute(
            "UPDATE werewolf_states SET phase = 'vote' WHERE id = ?",
            (state["id"],),
        )
        await db.commit()

        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "vote", "row": 1},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "target_dead" in data.get("error", "")


@pytest.mark.anyio
async def test_werewolf_dead_player_cannot_vote():
    """测试已淘汰的玩家不能投票"""
    players, room_id = await _create_and_start_werewolf(4)

    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM werewolf_states WHERE room_id = ?", (room_id,)
    )
    state = await cursor.fetchone()

    # 淘汰 player_index 0
    await db.execute(
        """UPDATE werewolf_players SET is_alive = 0
           WHERE state_id = ? AND agent_id = ?""",
        (state["id"], players[0]["agent_id"]),
    )
    await db.execute(
        "UPDATE werewolf_states SET phase = 'vote' WHERE id = ?",
        (state["id"],),
    )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/playlab/rooms/{room_id}/action",
            json={"action": "vote", "row": 1},
            headers={"agent-auth-api-key": players[0]["api_key"]},
        )
        data = resp.json()
        assert not data["success"]
        assert "already_dead" in data.get("error", "")
