"""PlayLab 游戏房间路由"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import CreateRoomRequest, GomokuActionRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

# 游戏类型定义：最大玩家数
GAME_TYPES = {
    "gomoku": {"name": "五子棋", "max_players": 2},
    "poker": {"name": "德州扑克", "max_players": 6},
    "werewolf": {"name": "谁是卧底", "max_players": 8},
}

router = APIRouter(prefix="/api/playlab", tags=["playlab"])


@router.post("/rooms")
async def create_room(
    req: CreateRoomRequest,
    agent: dict = Depends(get_current_agent),
):
    """创建游戏房间（需要 API Key），创建者自动加入"""
    db = await get_db()

    # 验证游戏类型
    if req.game_type not in GAME_TYPES:
        return error_response("invalid_game_type", f"不支持的游戏类型: {req.game_type}")

    game_info = GAME_TYPES[req.game_type]
    room_id = str(uuid.uuid4())
    player_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # 创建房间
    await db.execute(
        """INSERT INTO game_rooms (id, game_type, status, max_players, current_players, winner_id, created_at, finished_at)
           VALUES (?, ?, 'waiting', ?, 1, NULL, ?, NULL)""",
        (room_id, req.game_type, game_info["max_players"], now),
    )

    # 创建者自动加入（player_index = 0）
    await db.execute(
        """INSERT INTO game_players (id, room_id, agent_id, player_index, score, joined_at)
           VALUES (?, ?, ?, 0, 0, ?)""",
        (player_id, room_id, agent["agent_id"], now),
    )
    await db.commit()

    return success_response(
        data={
            "id": room_id,
            "game_type": req.game_type,
            "game_name": game_info["name"],
            "status": "waiting",
            "max_players": game_info["max_players"],
            "current_players": 1,
            "created_at": now,
            "creator": {
                "agent_id": agent["agent_id"],
                "username": agent["username"],
                "player_index": 0,
            },
        },
        message="房间创建成功",
    )


@router.get("/rooms")
async def list_rooms(page: int = 1, limit: int = 20):
    """获取等待中的房间列表（无需认证），分页"""
    db = await get_db()

    offset = (page - 1) * limit

    # 查询总数
    cursor = await db.execute(
        "SELECT COUNT(*) as total FROM game_rooms WHERE status = 'waiting'"
    )
    total = (await cursor.fetchone())["total"]

    # 查询房间列表
    cursor = await db.execute(
        """SELECT r.id, r.game_type, r.status, r.max_players, r.current_players, r.created_at,
                  p.agent_id as creator_id, a.username as creator_username, a.nickname as creator_nickname
           FROM game_rooms r
           JOIN game_players p ON r.id = p.room_id AND p.player_index = 0
           JOIN agents a ON p.agent_id = a.agent_id
           WHERE r.status = 'waiting'
           ORDER BY r.created_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    rows = await cursor.fetchall()

    rooms = [
        {
            "id": row["id"],
            "game_type": row["game_type"],
            "game_name": GAME_TYPES.get(row["game_type"], {}).get("name", row["game_type"]),
            "status": row["status"],
            "max_players": row["max_players"],
            "current_players": row["current_players"],
            "creator": {
                "agent_id": row["creator_id"],
                "username": row["creator_username"],
                "nickname": row["creator_nickname"],
            },
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return success_response(
        data={
            "rooms": rooms,
            "total": total,
            "page": page,
            "limit": limit,
        },
        message="获取房间列表成功",
    )


@router.post("/rooms/{room_id}/join")
async def join_room(
    room_id: str,
    agent: dict = Depends(get_current_agent),
):
    """加入游戏房间（需要 API Key），房间未满且未开始才可加入"""
    db = await get_db()

    # 查询房间
    cursor = await db.execute(
        "SELECT id, game_type, status, max_players, current_players FROM game_rooms WHERE id = ?",
        (room_id,),
    )
    room = await cursor.fetchone()

    if not room:
        return error_response("not_found", "房间不存在")

    if room["status"] != "waiting":
        return error_response("room_not_waiting", "房间已经开始或结束，无法加入")

    # 检查是否已在房间中
    cursor = await db.execute(
        "SELECT id FROM game_players WHERE room_id = ? AND agent_id = ?",
        (room_id, agent["agent_id"]),
    )
    if await cursor.fetchone():
        return error_response("already_joined", "你已经在这个房间中")

    # 检查房间是否已满
    if room["current_players"] >= room["max_players"]:
        return error_response("room_full", "房间已满，无法加入")

    # 加入房间
    player_id = str(uuid.uuid4())
    player_index = room["current_players"]
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO game_players (id, room_id, agent_id, player_index, score, joined_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (player_id, room_id, agent["agent_id"], player_index, now),
    )
    await db.execute(
        "UPDATE game_rooms SET current_players = current_players + 1 WHERE id = ?",
        (room_id,),
    )
    await db.commit()

    return success_response(
        data={
            "room_id": room_id,
            "player_index": player_index,
            "game_type": room["game_type"],
            "current_players": room["current_players"] + 1,
            "max_players": room["max_players"],
        },
        message="成功加入房间",
    )


@router.post("/rooms/{room_id}/start")
async def start_room(
    room_id: str,
    agent: dict = Depends(get_current_agent),
):
    """开始游戏（需要 API Key 且是创建者），房间满员后开始"""
    db = await get_db()

    # 查询房间
    cursor = await db.execute(
        "SELECT id, game_type, status, max_players, current_players FROM game_rooms WHERE id = ?",
        (room_id,),
    )
    room = await cursor.fetchone()

    if not room:
        return error_response("not_found", "房间不存在")

    if room["status"] != "waiting":
        return error_response("room_not_waiting", "房间已经开始或结束")

    # 检查是否是创建者（player_index = 0）
    cursor = await db.execute(
        "SELECT agent_id FROM game_players WHERE room_id = ? AND player_index = 0",
        (room_id,),
    )
    creator = await cursor.fetchone()

    if not creator or creator["agent_id"] != agent["agent_id"]:
        return error_response("not_creator", "只有房间创建者才能开始游戏")

    # 检查房间是否满员
    if room["current_players"] < room["max_players"]:
        return error_response("room_not_full", f"房间未满，还需要 {room['max_players'] - room['current_players']} 人")

    # 开始游戏
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE game_rooms SET status = 'playing' WHERE id = ?",
        (room_id,),
    )

    # 如果是五子棋，初始化棋盘状态
    if room["game_type"] == "gomoku":
        board = [[0] * 15 for _ in range(15)]
        state_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO game_states (id, room_id, board, current_turn, last_move, move_count)
               VALUES (?, ?, ?, 0, NULL, 0)""",
            (state_id, room_id, json.dumps(board)),
        )

    await db.commit()

    # 获取玩家列表
    cursor = await db.execute(
        """SELECT gp.player_index, gp.agent_id, a.username, a.nickname, a.avatar_url
           FROM game_players gp
           JOIN agents a ON gp.agent_id = a.agent_id
           WHERE gp.room_id = ?
           ORDER BY gp.player_index""",
        (room_id,),
    )
    players = [
        {
            "player_index": row["player_index"],
            "agent_id": row["agent_id"],
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_url": row["avatar_url"],
        }
        for row in await cursor.fetchall()
    ]

    return success_response(
        data={
            "room_id": room_id,
            "game_type": room["game_type"],
            "game_name": GAME_TYPES.get(room["game_type"], {}).get("name", room["game_type"]),
            "status": "playing",
            "players": players,
            "started_at": now,
        },
        message="游戏开始",
    )


@router.get("/rooms/{room_id}/state")
async def get_room_state(
    room_id: str,
    agent: dict = Depends(get_current_agent),
):
    """查看游戏状态（需要 API Key 且是参与者）"""
    db = await get_db()

    # 查询房间
    cursor = await db.execute(
        "SELECT id, game_type, status, max_players, current_players, winner_id, created_at, finished_at FROM game_rooms WHERE id = ?",
        (room_id,),
    )
    room = await cursor.fetchone()

    if not room:
        return error_response("not_found", "房间不存在")

    # 检查是否是参与者
    cursor = await db.execute(
        "SELECT id, player_index FROM game_players WHERE room_id = ? AND agent_id = ?",
        (room_id, agent["agent_id"]),
    )
    player = await cursor.fetchone()

    if not player:
        return error_response("not_player", "你不是该房间的参与者")

    # 获取所有玩家信息
    cursor = await db.execute(
        """SELECT gp.player_index, gp.agent_id, gp.score, a.username, a.nickname, a.avatar_url
           FROM game_players gp
           JOIN agents a ON gp.agent_id = a.agent_id
           WHERE gp.room_id = ?
           ORDER BY gp.player_index""",
        (room_id,),
    )
    players = [
        {
            "player_index": row["player_index"],
            "agent_id": row["agent_id"],
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_url": row["avatar_url"],
            "score": row["score"],
        }
        for row in await cursor.fetchall()
    ]

    state = {
        "room_id": room["id"],
        "game_type": room["game_type"],
        "game_name": GAME_TYPES.get(room["game_type"], {}).get("name", room["game_type"]),
        "status": room["status"],
        "max_players": room["max_players"],
        "current_players": room["current_players"],
        "players": players,
        "my_player_index": player["player_index"],
        "created_at": room["created_at"],
    }

    if room["winner_id"]:
        state["winner_id"] = room["winner_id"]
    if room["finished_at"]:
        state["finished_at"] = room["finished_at"]

    # 五子棋：附加棋盘状态
    if room["game_type"] == "gomoku":
        cursor = await db.execute(
            "SELECT board, current_turn, last_move, move_count FROM game_states WHERE room_id = ?",
            (room_id,),
        )
        gstate = await cursor.fetchone()
        if gstate:
            state["board"] = json.loads(gstate["board"])
            state["current_turn"] = gstate["current_turn"]
            state["last_move"] = json.loads(gstate["last_move"]) if gstate["last_move"] else None
            state["move_count"] = gstate["move_count"]

    return success_response(
        data=state,
        message="获取游戏状态成功",
    )


BOARD_SIZE = 15


def _check_win(board: list[list[int]], row: int, col: int, player: int) -> bool:
    """检查五子连珠（横/竖/对角线）"""
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dr, dc in directions:
        count = 1
        for sign in (1, -1):
            r, c = row + dr * sign, col + dc * sign
            while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and board[r][c] == player:
                count += 1
                r += dr * sign
                c += dc * sign
        if count >= 5:
            return True
    return False


@router.post("/rooms/{room_id}/action")
async def game_action(
    room_id: str,
    req: GomokuActionRequest,
    agent: dict = Depends(get_current_agent),
):
    """提交游戏操作（需要 API Key 且是参与者）"""
    db = await get_db()

    # 查询房间
    cursor = await db.execute(
        "SELECT id, game_type, status, max_players, current_players, winner_id FROM game_rooms WHERE id = ?",
        (room_id,),
    )
    room = await cursor.fetchone()

    if not room:
        return error_response("not_found", "房间不存在")

    if room["status"] != "playing":
        return error_response("game_not_playing", "游戏未在进行中")

    # 检查是否是参与者
    cursor = await db.execute(
        "SELECT id, player_index FROM game_players WHERE room_id = ? AND agent_id = ?",
        (room_id, agent["agent_id"]),
    )
    player = await cursor.fetchone()

    if not player:
        return error_response("not_player", "你不是该房间的参与者")

    # 五子棋逻辑
    if room["game_type"] == "gomoku":
        return await _gomoku_action(db, room, player, req)

    return error_response("unsupported_game", f"游戏类型 {room['game_type']} 暂不支持操作")


async def _gomoku_action(db, room, player, req: GomokuActionRequest):
    """五子棋操作处理"""
    if req.action != "place":
        return error_response("invalid_action", f"五子棋不支持操作: {req.action}")

    if req.row is None or req.col is None:
        return error_response("missing_params", "落子需要 row 和 col 参数")

    # 获取棋盘状态
    cursor = await db.execute(
        "SELECT id, board, current_turn, move_count FROM game_states WHERE room_id = ?",
        (room["id"],),
    )
    gstate = await cursor.fetchone()

    if not gstate:
        return error_response("no_game_state", "游戏状态不存在")

    # 检查轮次
    if gstate["current_turn"] != player["player_index"]:
        return error_response("not_your_turn", "还没轮到你落子")

    board = json.loads(gstate["board"])
    row, col = req.row, req.col

    # 检查位置是否为空
    if board[row][col] != 0:
        return error_response("position_occupied", "该位置已有棋子")

    # 落子（player_index 0 → 黑 1, player_index 1 → 白 2）
    piece = player["player_index"] + 1
    board[row][col] = piece
    move_count = gstate["move_count"] + 1
    last_move = json.dumps({"row": row, "col": col})
    next_turn = 1 - gstate["current_turn"]

    # 检查胜负
    winner_id = None
    finished_at = None
    new_status = "playing"

    if _check_win(board, row, col, piece):
        winner_id = player["player_index"]
        new_status = "finished"
        finished_at = datetime.now(timezone.utc).isoformat()
    elif move_count >= BOARD_SIZE * BOARD_SIZE:
        # 平局
        new_status = "finished"
        finished_at = datetime.now(timezone.utc).isoformat()

    # 更新棋盘状态
    await db.execute(
        """UPDATE game_states SET board = ?, current_turn = ?, last_move = ?, move_count = ?
           WHERE room_id = ?""",
        (json.dumps(board), next_turn, last_move, move_count, room["id"]),
    )

    # 更新房间状态（如果有赢家或平局）
    if new_status == "finished":
        await db.execute(
            "UPDATE game_rooms SET status = 'finished', winner_id = ?, finished_at = ? WHERE id = ?",
            (winner_id, finished_at, room["id"]),
        )

    await db.commit()

    result = {
        "room_id": room["id"],
        "action": "place",
        "row": row,
        "col": col,
        "piece": piece,
        "current_turn": next_turn,
        "move_count": move_count,
        "status": new_status,
    }

    if winner_id is not None:
        # 获取赢家 agent_id
        cursor = await db.execute(
            "SELECT agent_id FROM game_players WHERE room_id = ? AND player_index = ?",
            (room["id"], winner_id),
        )
        winner_row = await cursor.fetchone()
        result["winner_id"] = winner_row["agent_id"] if winner_row else None
        result["message"] = "恭喜获胜！"
    elif new_status == "finished":
        result["message"] = "平局！"
    else:
        result["message"] = "落子成功"

    return success_response(data=result, message=result.pop("message"))
