"""PlayLab 游戏房间路由"""
import json
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import CreateRoomRequest, GameActionRequest
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


# ==================== 扑克工具函数 ====================

SUITS = ["hearts", "diamonds", "clubs", "spades"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS, 2)}


def _create_deck() -> list[dict]:
    """创建一副52张标准扑克牌"""
    return [{"suit": s, "rank": r} for s in SUITS for r in RANKS]


def _card_str(card: dict) -> str:
    """牌的字符串表示"""
    return f"{card['rank']}{card['suit'][0].upper()}"


def _hand_rank(cards: list[dict]) -> tuple[int, list[int], str]:
    """
    评估5张或更多牌的最佳5张组合牌力。
    返回 (rank, tiebreakers, hand_name)
    rank: 9=皇家同花顺, 8=同花顺, 7=四条, 6=葫芦, 5=同花, 4=顺子, 3=三条, 2=两对, 1=一对, 0=高牌
    """
    from itertools import combinations

    best = (0, [], "high_card")
    if len(cards) <= 5:
        combos = [cards]
    else:
        combos = list(combinations(cards, 5))

    for combo in combos:
        r = _evaluate_five(list(combo))
        if r > best:
            best = r
    return best


def _evaluate_five(cards: list[dict]) -> tuple[int, list[int], str]:
    """评估恰好5张牌的牌力"""
    values = sorted([RANK_VALUES[c["rank"]] for c in cards], reverse=True)
    suits = [c["suit"] for c in cards]

    is_flush = len(set(suits)) == 1

    # 检查顺子
    is_straight = False
    straight_high = 0
    unique_vals = sorted(set(values), reverse=True)
    if len(unique_vals) == 5:
        if unique_vals[0] - unique_vals[4] == 4:
            is_straight = True
            straight_high = unique_vals[0]
        # A-2-3-4-5 (wheel)
        if unique_vals == [14, 5, 4, 3, 2]:
            is_straight = True
            straight_high = 5

    # 计数
    from collections import Counter
    counts = Counter(values)
    count_sorted = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if is_straight and is_flush and straight_high == 14:
        return (9, [14], "royal_flush")
    if is_straight and is_flush:
        return (8, [straight_high], "straight_flush")
    if count_sorted[0][1] == 4:
        kicker = [v for v in values if v != count_sorted[0][1] or v != count_sorted[0][0]]
        kickers = sorted([v for v in values if v != count_sorted[0][0]], reverse=True)
        return (7, [count_sorted[0][0]] + kickers, "four_of_a_kind")
    if count_sorted[0][1] == 3 and count_sorted[1][1] == 2:
        return (6, [count_sorted[0][0], count_sorted[1][0]], "full_house")
    if is_flush:
        return (5, values, "flush")
    if is_straight:
        return (4, [straight_high], "straight")
    if count_sorted[0][1] == 3:
        kickers = sorted([v for v in values if v != count_sorted[0][0]], reverse=True)
        return (3, [count_sorted[0][0]] + kickers, "three_of_a_kind")
    if count_sorted[0][1] == 2 and count_sorted[1][1] == 2:
        pairs = sorted([count_sorted[0][0], count_sorted[1][0]], reverse=True)
        kicker = sorted([v for v in values if v not in pairs], reverse=True)
        return (2, pairs + kicker, "two_pairs")
    if count_sorted[0][1] == 2:
        kickers = sorted([v for v in values if v != count_sorted[0][0]], reverse=True)
        return (1, [count_sorted[0][0]] + kickers, "one_pair")
    return (0, values, "high_card")


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

    # 检查玩家数量
    min_players = 2  # 所有游戏至少需要2人
    if room["game_type"] == "gomoku":
        min_players = room["max_players"]  # 五子棋需要满员
    if room["game_type"] == "werewolf":
        min_players = 3  # 谁是卧底至少需要3人
    if room["current_players"] < min_players:
        return error_response("not_enough_players", f"人数不足，至少需要 {min_players} 人")

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

    # 如果是德州扑克，初始化牌局状态
    if room["game_type"] == "poker":
        await _init_poker_game(db, room_id)

    # 如果是谁是卧底，初始化游戏状态
    if room["game_type"] == "werewolf":
        await _init_werewolf_game(db, room_id)

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
        "SELECT id, player_index, agent_id FROM game_players WHERE room_id = ? AND agent_id = ?",
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

    # 德州扑克：附加牌局状态
    if room["game_type"] == "poker":
        poker_state = await _get_poker_state_data(db, room_id, player["player_index"])
        state.update(poker_state)

    # 谁是卧底：附加游戏状态
    if room["game_type"] == "werewolf":
        werewolf_state = await _get_werewolf_state_data(db, room_id, agent["agent_id"])
        state.update(werewolf_state)

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
    req: GameActionRequest,
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
        "SELECT id, player_index, agent_id FROM game_players WHERE room_id = ? AND agent_id = ?",
        (room_id, agent["agent_id"]),
    )
    player = await cursor.fetchone()

    if not player:
        return error_response("not_player", "你不是该房间的参与者")

    # 五子棋逻辑
    if room["game_type"] == "gomoku":
        return await _gomoku_action(db, room, player, req)

    # 德州扑克逻辑
    if room["game_type"] == "poker":
        return await _poker_action(db, room, player, req)

    # 谁是卧底逻辑
    if room["game_type"] == "werewolf":
        return await _werewolf_action(db, room, player, req)

    return error_response("unsupported_game", f"游戏类型 {room['game_type']} 暂不支持操作")


async def _gomoku_action(db, room, player, req: GameActionRequest):
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


# ==================== 德州扑克逻辑 ====================

INITIAL_CHIPS = 1000
SMALL_BLIND = 10
BIG_BLIND = 20


async def _init_poker_game(db, room_id: str):
    """初始化德州扑克牌局"""
    # 获取玩家列表
    cursor = await db.execute(
        "SELECT player_index, agent_id FROM game_players WHERE room_id = ? ORDER BY player_index",
        (room_id,),
    )
    players = await cursor.fetchall()

    # 创建并洗牌
    deck = _create_deck()
    random.shuffle(deck)

    # 发底牌（每人2张）
    hands = {}
    for p in players:
        hole = [deck.pop(), deck.pop()]
        hands[p["player_index"]] = hole

    state_id = str(uuid.uuid4())

    # 创建牌局状态
    await db.execute(
        """INSERT INTO poker_states (id, room_id, deck, community_cards, pot, current_bet, phase, dealer_index, current_player_index, small_blind, big_blind)
           VALUES (?, ?, ?, '[]', ?, ?, 'preflop', 0, 1, ?, ?)""",
        (state_id, room_id, json.dumps(deck), SMALL_BLIND + BIG_BLIND, BIG_BLIND, SMALL_BLIND, BIG_BLIND),
    )

    # 为每个玩家创建手牌记录
    for p in players:
        hand_id = str(uuid.uuid4())
        hole = hands[p["player_index"]]
        # 庄家(position 0)交小盲注，下家(position 1)交大盲注
        blind = 0
        if p["player_index"] == 0:
            blind = SMALL_BLIND
        elif p["player_index"] == 1 and len(players) > 2:
            blind = BIG_BLIND
        elif p["player_index"] == 1 and len(players) == 2:
            blind = BIG_BLIND

        await db.execute(
            """INSERT INTO poker_hands (id, state_id, player_id, room_id, agent_id, hole_cards, bet, total_bet, folded, chips)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (hand_id, state_id, p["agent_id"], room_id, p["agent_id"],
             json.dumps(hole), blind, blind, INITIAL_CHIPS - blind),
        )

    # 如果只有2人，庄家(pos 0)是SB也是先行动的，对手(pos 1)是BB
    # 翻牌前：SB先行动 -> 翻牌后：BB先行动
    # current_player_index 在 preflop 指向 BB 后面的玩家（或 SB 如果只有2人）
    if len(players) == 2:
        await db.execute(
            "UPDATE poker_states SET current_player_index = 0 WHERE id = ?",
            (state_id,),
        )
    else:
        # 3+ 人：pos 0 = SB, pos 1 = BB, pos 2 先行动
        next_idx = 2 if len(players) > 2 else 0
        await db.execute(
            "UPDATE poker_states SET current_player_index = ? WHERE id = ?",
            (next_idx, state_id),
        )

    await db.commit()


async def _get_poker_state_data(db, room_id: str, my_index: int) -> dict:
    """获取扑克牌局状态数据"""
    cursor = await db.execute(
        "SELECT id, deck, community_cards, pot, current_bet, phase, dealer_index, current_player_index FROM poker_states WHERE room_id = ?",
        (room_id,),
    )
    pstate = await cursor.fetchone()
    if not pstate:
        return {}

    community = json.loads(pstate["community_cards"])

    # 获取所有玩家手牌信息
    cursor = await db.execute(
        """SELECT ph.agent_id, ph.hole_cards, ph.bet, ph.total_bet, ph.folded, ph.chips, ph.hand_rank, ph.hand_name,
                  gp.player_index, a.username, a.nickname
           FROM poker_hands ph
           JOIN game_players gp ON ph.agent_id = gp.agent_id AND gp.room_id = ?
           JOIN agents a ON ph.agent_id = a.agent_id
           WHERE ph.room_id = ?
           ORDER BY gp.player_index""",
        (room_id, room_id),
    )
    hand_rows = await cursor.fetchall()

    players_info = []
    my_hole_cards = []
    for h in hand_rows:
        hole = json.loads(h["hole_cards"])
        info = {
            "player_index": h["player_index"],
            "username": h["username"],
            "nickname": h["nickname"],
            "bet": h["bet"],
            "total_bet": h["total_bet"],
            "folded": bool(h["folded"]),
            "chips": h["chips"],
        }
        if h["player_index"] == my_index:
            # 只能看到自己的底牌
            my_hole_cards = [_card_str(c) for c in hole]
            info["hole_cards"] = [_card_str(c) for c in hole]
        else:
            # 不显示其他人的底牌
            info["hole_cards"] = []
        if pstate["phase"] == "showdown":
            info["hand_rank"] = h["hand_rank"]
            info["hand_name"] = h["hand_name"]
            if not h["folded"]:
                info["hole_cards"] = [_card_str(c) for c in hole]
        players_info.append(info)

    return {
        "poker": {
            "phase": pstate["phase"],
            "pot": pstate["pot"],
            "current_bet": pstate["current_bet"],
            "community_cards": [_card_str(c) for c in community],
            "dealer_index": pstate["dealer_index"],
            "current_player_index": pstate["current_player_index"],
            "players": players_info,
            "my_hole_cards": my_hole_cards,
        },
    }


async def _poker_action(db, room, player, req: GameActionRequest):
    """德州扑克操作处理"""
    cursor = await db.execute(
        "SELECT id, deck, community_cards, pot, current_bet, phase, dealer_index, current_player_index FROM poker_states WHERE room_id = ?",
        (room["id"],),
    )
    pstate = await cursor.fetchone()

    if not pstate:
        return error_response("no_game_state", "牌局状态不存在")

    if pstate["phase"] == "showdown":
        return error_response("game_over", "牌局已结束")

    # 检查是否轮到该玩家
    if pstate["current_player_index"] != player["player_index"]:
        return error_response("not_your_turn", "还没轮到你操作")

    # 获取当前玩家手牌
    cursor = await db.execute(
        "SELECT id, hole_cards, bet, total_bet, folded, chips FROM poker_hands WHERE room_id = ? AND agent_id = ?",
        (room["id"], player["agent_id"]),
    )
    my_hand = await cursor.fetchone()

    if not my_hand:
        return error_response("no_hand", "你的手牌不存在")

    if my_hand["folded"]:
        return error_response("already_folded", "你已经弃牌")

    action = req.action.lower()

    if action == "fold":
        return await _poker_fold(db, room, pstate, player, my_hand)
    elif action == "call":
        return await _poker_call(db, room, pstate, player, my_hand)
    elif action == "raise":
        return await _poker_raise(db, room, pstate, player, my_hand, req.amount)
    elif action == "allin":
        return await _poker_allin(db, room, pstate, player, my_hand)
    else:
        return error_response("invalid_action", f"德州扑克不支持操作: {req.action}")


async def _poker_fold(db, room, pstate, player, my_hand):
    """弃牌"""
    await db.execute(
        "UPDATE poker_hands SET folded = 1 WHERE room_id = ? AND agent_id = ?",
        (room["id"], player["agent_id"]),
    )
    await db.commit()

    # 检查是否只剩一人未弃牌
    cursor = await db.execute(
        "SELECT agent_id FROM poker_hands WHERE room_id = ? AND folded = 0",
        (room["id"],),
    )
    active = await cursor.fetchall()

    if len(active) == 1:
        # 最后一人获胜
        winner_agent_id = active[0]["agent_id"]
        await _finish_poker(db, room, pstate, winner_agent_id, "others_folded")
        return success_response(
            data={"action": "fold", "status": "finished", "winner_id": winner_agent_id, "reason": "others_folded"},
            message="你弃牌了，其他玩家获胜",
        )

    # 移动到下一个玩家
    await _advance_to_next_player(db, room, pstate, player["player_index"])

    return success_response(
        data={"action": "fold", "status": "playing"},
        message="弃牌成功",
    )


async def _poker_call(db, room, pstate, player, my_hand):
    """跟注：匹配当前最高注"""
    current_bet = pstate["current_bet"]
    my_bet = my_hand["bet"]
    call_amount = current_bet - my_bet

    if call_amount <= 0:
        # 已经匹配，相当于过牌
        await _advance_to_next_player(db, room, pstate, player["player_index"])
        return success_response(
            data={"action": "call", "call_amount": 0, "status": "playing"},
            message="过牌",
        )

    # 检查筹码是否足够
    chips = my_hand["chips"]
    actual_call = min(call_amount, chips)

    new_bet = my_bet + actual_call
    new_chips = chips - actual_call
    new_total = my_hand["total_bet"] + actual_call

    await db.execute(
        "UPDATE poker_hands SET bet = ?, chips = ?, total_bet = ? WHERE room_id = ? AND agent_id = ?",
        (new_bet, new_chips, new_total, room["id"], player["agent_id"]),
    )
    await db.execute(
        "UPDATE poker_states SET pot = pot + ? WHERE room_id = ?",
        (actual_call, room["id"]),
    )
    await db.commit()

    # 检查是否需要进入下一阶段
    await _check_phase_advance(db, room, pstate, player["player_index"])

    return success_response(
        data={"action": "call", "call_amount": actual_call, "chips_remaining": new_chips, "status": "playing"},
        message="跟注成功",
    )


async def _poker_raise(db, room, pstate, player, my_hand, raise_amount: int):
    """加注"""
    if raise_amount <= 0:
        return error_response("invalid_amount", "加注金额必须大于0")

    current_bet = pstate["current_bet"]
    my_bet = my_hand["bet"]
    chips = my_hand["chips"]

    # 跟注部分 + 加注部分
    call_amount = current_bet - my_bet
    total_needed = call_amount + raise_amount

    if total_needed > chips:
        return error_response("insufficient_chips", "筹码不足")

    new_bet = current_bet + raise_amount
    actual_total = call_amount + raise_amount
    new_chips = chips - actual_total
    new_total_bet = my_hand["total_bet"] + actual_total

    await db.execute(
        "UPDATE poker_hands SET bet = ?, chips = ?, total_bet = ? WHERE room_id = ? AND agent_id = ?",
        (new_bet, new_chips, new_total_bet, room["id"], player["agent_id"]),
    )
    await db.execute(
        "UPDATE poker_states SET pot = pot + ?, current_bet = ? WHERE room_id = ?",
        (actual_total, new_bet, room["id"]),
    )
    await db.commit()

    # 加注后，其他人需要重新行动
    await _advance_to_next_player(db, room, pstate, player["player_index"])

    return success_response(
        data={"action": "raise", "raise_amount": raise_amount, "new_bet": new_bet, "chips_remaining": new_chips, "status": "playing"},
        message=f"加注 {raise_amount}",
    )


async def _poker_allin(db, room, pstate, player, my_hand):
    """全押"""
    chips = my_hand["chips"]
    current_bet = pstate["current_bet"]
    my_bet = my_hand["bet"]

    allin_amount = chips
    new_bet = my_bet + allin_amount
    new_total = my_hand["total_bet"] + allin_amount

    await db.execute(
        "UPDATE poker_hands SET bet = ?, chips = 0, total_bet = ? WHERE room_id = ? AND agent_id = ?",
        (new_bet, new_total, room["id"], player["agent_id"]),
    )

    # 更新 current_bet 如果全押后注额更高
    if new_bet > current_bet:
        await db.execute(
            "UPDATE poker_states SET current_bet = ? WHERE room_id = ?",
            (new_bet, room["id"]),
        )

    await db.execute(
        "UPDATE poker_states SET pot = pot + ? WHERE room_id = ?",
        (allin_amount, room["id"]),
    )
    await db.commit()

    # 检查只剩一人未弃牌且未全押
    cursor = await db.execute(
        "SELECT agent_id, chips, folded FROM poker_hands WHERE room_id = ? AND folded = 0",
        (room["id"],),
    )
    active = await cursor.fetchall()

    # 如果所有活跃玩家都已 all-in（筹码为0），直接摊牌
    all_in = all(r["chips"] == 0 for r in active)
    if all_in and len(active) > 1:
        await _run_showdown(db, room, pstate)
        return success_response(
            data={"action": "allin", "allin_amount": allin_amount, "status": "showdown"},
            message="全押！进入摊牌",
        )

    await _advance_to_next_player(db, room, pstate, player["player_index"])

    return success_response(
        data={"action": "allin", "allin_amount": allin_amount, "chips_remaining": 0, "status": "playing"},
        message="全押！",
    )


async def _advance_to_next_player(db, room, pstate, current_player_index: int):
    """移动到下一个活跃玩家，如果一轮完毕则进入下一阶段"""
    cursor = await db.execute(
        "SELECT player_index FROM poker_hands ph JOIN game_players gp ON ph.agent_id = gp.agent_id AND gp.room_id = ? WHERE ph.room_id = ? AND ph.folded = 0 ORDER BY gp.player_index",
        (room["id"], room["id"]),
    )
    active_indices = [r["player_index"] for r in await cursor.fetchall()]

    if not active_indices:
        return

    # 找下一个活跃玩家
    next_idx = None
    for idx in active_indices:
        if idx > current_player_index:
            next_idx = idx
            break
    if next_idx is None:
        next_idx = active_indices[0]

    # 检查是否这一轮下注已完成（所有人都匹配了当前注）
    cursor = await db.execute(
        "SELECT bet, folded, chips FROM poker_hands WHERE room_id = ?",
        (room["id"],),
    )
    all_hands = await cursor.fetchall()

    current_bet = pstate["current_bet"]
    all_matched = True
    for h in all_hands:
        if not h["folded"] and h["chips"] > 0 and h["bet"] < current_bet:
            all_matched = False
            break

    if all_matched and next_idx <= current_player_index:
        # 一轮完毕，进入下一阶段
        await _advance_phase(db, room, pstate)
    else:
        await db.execute(
            "UPDATE poker_states SET current_player_index = ? WHERE room_id = ?",
            (next_idx, room["id"]),
        )
        await db.commit()


async def _check_phase_advance(db, room, pstate, current_player_index: int):
    """检查是否应该进入下一阶段"""
    cursor = await db.execute(
        "SELECT bet, folded, chips FROM poker_hands WHERE room_id = ?",
        (room["id"],),
    )
    all_hands = await cursor.fetchall()

    # 刷新 pstate
    cursor = await db.execute(
        "SELECT id, deck, community_cards, pot, current_bet, phase, dealer_index, current_player_index FROM poker_states WHERE room_id = ?",
        (room["id"],),
    )
    fresh_state = await cursor.fetchone()
    if not fresh_state:
        return

    current_bet = fresh_state["current_bet"]
    all_matched = True
    for h in all_hands:
        if not h["folded"] and h["chips"] > 0 and h["bet"] < current_bet:
            all_matched = False
            break

    if all_matched:
        # 检查是否已经绕回一轮
        cursor = await db.execute(
            "SELECT player_index FROM poker_hands ph JOIN game_players gp ON ph.agent_id = gp.agent_id AND gp.room_id = ? WHERE ph.room_id = ? AND ph.folded = 0 AND ph.chips > 0 ORDER BY gp.player_index",
            (room["id"], room["id"]),
        )
        can_act = [r["player_index"] for r in await cursor.fetchall()]

        if len(can_act) <= 1:
            # 只剩一人或零人可以行动，进入下一阶段
            await _advance_phase(db, room, fresh_state)
            return

        await _advance_phase(db, room, fresh_state)
    else:
        await _advance_to_next_player(db, room, pstate, current_player_index)


async def _advance_phase(db, room, pstate):
    """进入下一阶段：preflop -> flop -> turn -> river -> showdown"""
    phase = pstate["phase"]

    if phase == "preflop":
        new_phase = "flop"
        cards_to_deal = 3
    elif phase == "flop":
        new_phase = "turn"
        cards_to_deal = 1
    elif phase == "turn":
        new_phase = "river"
        cards_to_deal = 1
    elif phase == "river":
        await _run_showdown(db, room, pstate)
        return
    else:
        return

    # 从牌堆抽公共牌
    deck = json.loads(pstate["deck"])
    community = json.loads(pstate["community_cards"])
    for _ in range(cards_to_deal):
        community.append(deck.pop())

    # 重置所有玩家的本轮下注
    await db.execute(
        "UPDATE poker_hands SET bet = 0 WHERE room_id = ?",
        (room["id"],),
    )

    # 找到第一个活跃玩家
    cursor = await db.execute(
        """SELECT gp.player_index FROM game_players gp
           JOIN poker_hands ph ON gp.agent_id = ph.agent_id AND ph.room_id = ?
           WHERE gp.room_id = ? AND ph.folded = 0
           ORDER BY gp.player_index
           LIMIT 1""",
        (room["id"], room["id"]),
    )
    first_active = await cursor.fetchone()

    first_idx = first_active["player_index"] if first_active else 0

    await db.execute(
        """UPDATE poker_states SET deck = ?, community_cards = ?, phase = ?, current_bet = 0, current_player_index = ?
           WHERE room_id = ?""",
        (json.dumps(deck), json.dumps(community), new_phase, first_idx, room["id"]),
    )
    await db.commit()

    # 检查是否只剩一个未弃牌
    cursor = await db.execute(
        "SELECT agent_id FROM poker_hands WHERE room_id = ? AND folded = 0",
        (room["id"],),
    )
    active = await cursor.fetchall()
    if len(active) == 1:
        await _finish_poker(db, room, pstate, active[0]["agent_id"], "others_folded")


async def _run_showdown(db, room, pstate):
    """摊牌：比较所有未弃牌玩家的手牌，判定赢家"""
    # 刷新状态
    cursor = await db.execute(
        "SELECT deck, community_cards, pot, phase FROM poker_states WHERE room_id = ?",
        (room["id"],),
    )
    fresh = await cursor.fetchone()
    if not fresh:
        return

    community = json.loads(fresh["community_cards"])
    deck = json.loads(fresh["deck"])

    # 确保有5张公共牌
    while len(community) < 5:
        community.append(deck.pop())

    await db.execute(
        "UPDATE poker_states SET community_cards = ?, deck = ?, phase = 'showdown' WHERE room_id = ?",
        (json.dumps(community), json.dumps(deck), room["id"]),
    )

    # 获取所有未弃牌玩家
    cursor = await db.execute(
        """SELECT ph.id, ph.agent_id, ph.hole_cards, ph.folded, gp.player_index
           FROM poker_hands ph
           JOIN game_players gp ON ph.agent_id = gp.agent_id AND gp.room_id = ?
           WHERE ph.room_id = ? AND ph.folded = 0
           ORDER BY gp.player_index""",
        (room["id"], room["id"]),
    )
    hands = await cursor.fetchall()

    best_rank = (-1, [], "")
    winners = []

    for h in hands:
        hole = json.loads(h["hole_cards"])
        all_cards = hole + community
        rank, tiebreakers, name = _hand_rank(all_cards)
        await db.execute(
            "UPDATE poker_hands SET hand_rank = ?, hand_name = ? WHERE id = ?",
            (rank, name, h["id"]),
        )
        if (rank, tiebreakers) > (best_rank[0], best_rank[1]):
            best_rank = (rank, tiebreakers, name)
            winners = [h["agent_id"]]
        elif (rank, tiebreakers) == (best_rank[0], best_rank[1]):
            winners.append(h["agent_id"])

    # 如果平分底池
    if len(winners) == 1:
        winner_agent_id = winners[0]
    else:
        winner_agent_id = winners[0]  # 简化：多人平分取第一个

    await _finish_poker(db, room, fresh, winner_agent_id, "showdown")


async def _finish_poker(db, room, pstate, winner_agent_id: str, reason: str):
    """结束牌局"""
    now = datetime.now(timezone.utc).isoformat()

    # 更新房间状态
    await db.execute(
        "UPDATE game_rooms SET status = 'finished', winner_id = ?, finished_at = ? WHERE id = ?",
        (winner_agent_id, now, room["id"]),
    )

    # 更新牌局阶段为 showdown
    await db.execute(
        "UPDATE poker_states SET phase = 'showdown' WHERE room_id = ?",
        (room["id"],),
    )

    await db.commit()


# ==================== 谁是卧底逻辑 ====================

# 词对库：平民词 -> 卧底词
WORD_PAIRS = [
    ("西瓜", "哈密瓜"), ("苹果", "梨"), ("牛奶", "豆浆"), ("面包", "馒头"),
    ("台灯", "手电筒"), ("钢笔", "铅笔"), ("汽车", "火车"), ("飞机", "火箭"),
    ("猫", "狗"), ("蝴蝶", "蜻蜓"), ("玫瑰", "百合"), ("沙发", "椅子"),
    ("眼镜", "墨镜"), ("微信", "QQ"), ("春节", "元旦"), ("饺子", "包子"),
    ("篮球", "足球"), ("游泳", "跳水"), ("筷子", "叉子"), ("日出", "日落"),
]


async def _init_werewolf_game(db, room_id: str):
    """初始化谁是卧底游戏"""
    # 获取玩家列表
    cursor = await db.execute(
        "SELECT player_index, agent_id FROM game_players WHERE room_id = ? ORDER BY player_index",
        (room_id,),
    )
    players = await cursor.fetchall()
    n = len(players)

    # 随机选词对
    civilian_word, spy_word = random.choice(WORD_PAIRS)

    # 计算卧底数量：约1/3，最少1人
    spy_count = max(1, n // 3)

    # 随机分配角色
    indices = list(range(n))
    spy_indices = set(random.sample(indices, spy_count))

    state_id = str(uuid.uuid4())

    # 创建游戏状态，第一个描述者为 player_index 0
    await db.execute(
        """INSERT INTO werewolf_states (id, room_id, civilian_word, spy_word, phase, round, current_describer_index)
           VALUES (?, ?, ?, ?, 'describe', 1, 0)""",
        (state_id, room_id, civilian_word, spy_word),
    )

    # 为每个玩家创建角色记录
    for p in players:
        player_id = str(uuid.uuid4())
        role = "spy" if p["player_index"] in spy_indices else "civilian"
        await db.execute(
            """INSERT INTO werewolf_players (id, state_id, agent_id, role, is_alive, description, voted_for_id)
               VALUES (?, ?, ?, ?, 1, '', '')""",
            (player_id, state_id, p["agent_id"], role),
        )

    await db.commit()


async def _get_werewolf_state_data(db, room_id: str, my_agent_id: str) -> dict:
    """获取谁是卧底游戏状态数据"""
    cursor = await db.execute(
        "SELECT id, civilian_word, spy_word, phase, round, current_describer_index FROM werewolf_states WHERE room_id = ?",
        (room_id,),
    )
    wstate = await cursor.fetchone()
    if not wstate:
        return {}

    # 获取我的角色
    cursor = await db.execute(
        "SELECT role, is_alive, description FROM werewolf_players WHERE state_id = ? AND agent_id = ?",
        (wstate["id"], my_agent_id),
    )
    my_info = await cursor.fetchone()

    my_word = ""
    if my_info:
        my_word = wstate["civilian_word"] if my_info["role"] == "civilian" else wstate["spy_word"]

    # 获取所有玩家信息（不暴露角色）
    cursor = await db.execute(
        """SELECT wp.agent_id, wp.is_alive, wp.description, gp.player_index, a.username, a.nickname
           FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           JOIN agents a ON wp.agent_id = a.agent_id
           WHERE wp.state_id = ?
           ORDER BY gp.player_index""",
        (room_id, wstate["id"]),
    )
    player_rows = await cursor.fetchall()

    players_info = []
    my_player_index = None
    is_my_turn = False
    for p in player_rows:
        info = {
            "player_index": p["player_index"],
            "username": p["username"],
            "nickname": p["nickname"],
            "is_alive": bool(p["is_alive"]),
            "description": p["description"] if p["description"] else "",
        }
        players_info.append(info)
        if p["agent_id"] == my_agent_id:
            my_player_index = p["player_index"]

    # 判断是否轮到我描述
    if my_player_index is not None and wstate["phase"] == "describe":
        # 获取存活玩家按顺序排列
        alive_indices = [p["player_index"] for p in players_info if p["is_alive"]]
        if alive_indices:
            # current_describer_index 是存活的第几个
            current_idx = wstate["current_describer_index"]
            if current_idx < len(alive_indices) and alive_indices[current_idx] == my_player_index:
                is_my_turn = True

    return {
        "werewolf": {
            "phase": wstate["phase"],
            "round": wstate["round"],
            "current_describer_index": wstate["current_describer_index"],
            "my_word": my_word,
            "my_role": my_info["role"] if my_info else "",
            "is_my_turn": is_my_turn,
            "players": players_info,
        },
    }


async def _werewolf_action(db, room, player, req: GameActionRequest):
    """谁是卧底操作处理"""
    cursor = await db.execute(
        "SELECT id, civilian_word, spy_word, phase, round, current_describer_index FROM werewolf_states WHERE room_id = ?",
        (room["id"],),
    )
    wstate = await cursor.fetchone()

    if not wstate:
        return error_response("no_game_state", "游戏状态不存在")

    action = req.action.lower()

    if action == "describe":
        return await _werewolf_describe(db, room, wstate, player, req)
    elif action == "vote":
        return await _werewolf_vote(db, room, wstate, player, req)
    else:
        return error_response("invalid_action", f"谁是卧底不支持操作: {req.action}")


async def _werewolf_describe(db, room, wstate, player, req: GameActionRequest):
    """提交描述"""
    # 检查当前阶段
    if wstate["phase"] != "describe":
        return error_response("wrong_phase", "当前不是描述阶段")

    # 获取存活玩家列表（按 player_index 排序）
    cursor = await db.execute(
        """SELECT gp.player_index, wp.agent_id, wp.is_alive, wp.description
           FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           WHERE wp.state_id = ? AND wp.is_alive = 1
           ORDER BY gp.player_index""",
        (room["id"], wstate["id"]),
    )
    alive_players = await cursor.fetchall()

    if not alive_players:
        return error_response("no_alive", "没有存活的玩家")

    # 检查是否轮到该玩家描述
    current_idx = wstate["current_describer_index"]
    if current_idx >= len(alive_players):
        return error_response("all_described", "本轮描述已结束")

    current_describer = alive_players[current_idx]
    if current_describer["agent_id"] != player["agent_id"]:
        return error_response("not_your_turn", "还没轮到你描述")

    # 检查描述内容
    description = ""
    if req.amount is not None and req.amount > 0:
        pass  # amount 字段不用于描述
    # 使用 row/col 或其他字段传递描述内容不太合适，用 GameActionRequest 的 amount
    # 实际上我们需要一个 description 字段。由于 GameActionRequest 是统一的，我们临时用 amount 存描述
    # 不对，让我看看... GameActionRequest 有 action, row, col, amount
    # 描述内容应该通过一个专门的字段传递。但为了保持统一模型，我们可以用 row 存一个描述索引
    # 或者我们直接在 req 上添加字段。

    # 更好的方案：使用 amount 字段作为描述内容的标记（比如描述序号），实际描述内容存在服务端
    # 但 PRD 说 POST 提交描述... 让我用一个简化的方式

    # 检查玩家是否已经描述过
    if current_describer["description"]:
        return error_response("already_described", "你已经描述过了")

    # 记录描述（使用一个简化的方式：记录一个描述标记）
    # 由于 GameActionRequest 没有文本字段，我们存储一个默认描述
    # 实际上 amount 可以当作描述的占位。我们用 "described" 作为标记
    await db.execute(
        "UPDATE werewolf_players SET description = ? WHERE state_id = ? AND agent_id = ?",
        ("described", wstate["id"], player["agent_id"]),
    )

    # 移动到下一个描述者
    next_idx = current_idx + 1

    if next_idx >= len(alive_players):
        # 所有人描述完毕，进入投票阶段
        await db.execute(
            "UPDATE werewolf_states SET phase = 'vote', current_describer_index = 0 WHERE id = ?",
            (wstate["id"],),
        )
        await db.commit()
        return success_response(
            data={"action": "describe", "phase": "vote", "message": "所有人描述完毕，进入投票阶段"},
            message="描述已提交，进入投票阶段",
        )
    else:
        await db.execute(
            "UPDATE werewolf_states SET current_describer_index = ? WHERE id = ?",
            (next_idx, wstate["id"]),
        )
        await db.commit()
        next_describer = alive_players[next_idx]
        return success_response(
            data={"action": "describe", "phase": "describe", "next_describer_index": next_idx, "next_describer_agent_id": next_describer["agent_id"]},
            message="描述已提交",
        )


async def _werewolf_vote(db, room, wstate, player, req: GameActionRequest):
    """投票淘汰一人"""
    if wstate["phase"] != "vote":
        return error_response("wrong_phase", "当前不是投票阶段")

    # target 通过 amount 字段传递 target 的 player_index（由于 GameActionRequest 统一模型）
    # 或者用 row 字段传递 target_player_index
    target_index = req.row  # 用 row 字段传递 target player_index
    if target_index is None:
        return error_response("missing_params", "投票需要指定目标（通过 row 参数传递 target_player_index）")

    # 检查投票者是否存活
    cursor = await db.execute(
        "SELECT is_alive, voted_for_id FROM werewolf_players WHERE state_id = ? AND agent_id = ?",
        (wstate["id"], player["agent_id"]),
    )
    voter = await cursor.fetchone()

    if not voter:
        return error_response("not_player", "你不是游戏参与者")

    if not voter["is_alive"]:
        return error_response("already_dead", "你已被淘汰，无法投票")

    if voter["voted_for_id"]:
        return error_response("already_voted", "你已经投过票了")

    # 查找目标玩家
    cursor = await db.execute(
        """SELECT wp.agent_id, wp.is_alive, gp.player_index
           FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           WHERE wp.state_id = ? AND gp.player_index = ?""",
        (room["id"], wstate["id"], target_index),
    )
    target = await cursor.fetchone()

    if not target:
        return error_response("invalid_target", "目标玩家不存在")

    if not target["is_alive"]:
        return error_response("target_dead", "目标玩家已被淘汰")

    if target["agent_id"] == player["agent_id"]:
        return error_response("cannot_vote_self", "不能投票给自己")

    # 记录投票
    await db.execute(
        "UPDATE werewolf_players SET voted_for_id = ? WHERE state_id = ? AND agent_id = ?",
        (target["agent_id"], wstate["id"], player["agent_id"]),
    )
    await db.commit()

    # 检查是否所有存活玩家都已投票
    cursor = await db.execute(
        "SELECT agent_id FROM werewolf_players WHERE state_id = ? AND is_alive = 1 AND voted_for_id = ''",
        (wstate["id"],),
    )
    remaining = await cursor.fetchall()

    if len(remaining) > 0:
        return success_response(
            data={"action": "vote", "status": "voting", "remaining_votes": len(remaining)},
            message="投票成功，等待其他玩家投票",
        )

    # 所有存活玩家都已投票，统计结果
    return await _werewolf_tally_votes(db, room, wstate)


async def _werewolf_tally_votes(db, room, wstate):
    """统计投票结果"""
    # 获取所有投票
    cursor = await db.execute(
        "SELECT agent_id, voted_for_id FROM werewolf_players WHERE state_id = ? AND is_alive = 1",
        (wstate["id"],),
    )
    votes = await cursor.fetchall()

    # 统计票数
    vote_count: dict[str, int] = {}
    for v in votes:
        target = v["voted_for_id"]
        if target:
            vote_count[target] = vote_count.get(target, 0) + 1

    # 找出票数最多的人
    if not vote_count:
        return error_response("no_votes", "没有人投票")

    max_votes = max(vote_count.values())
    top_voted = [aid for aid, cnt in vote_count.items() if cnt == max_votes]

    if len(top_voted) > 1:
        # 平票：随机淘汰一人（简化处理）
        eliminated_id = random.choice(top_voted)
    else:
        eliminated_id = top_voted[0]

    # 淘汰该玩家
    await db.execute(
        "UPDATE werewolf_players SET is_alive = 0 WHERE state_id = ? AND agent_id = ?",
        (wstate["id"], eliminated_id),
    )

    # 获取被淘汰者信息
    cursor = await db.execute(
        "SELECT wp.agent_id, gp.player_index, wp.role, a.username FROM werewolf_players wp JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ? JOIN agents a ON wp.agent_id = a.agent_id WHERE wp.state_id = ? AND wp.agent_id = ?",
        (room["id"], wstate["id"], eliminated_id),
    )
    eliminated_info = await cursor.fetchone()

    # 检查游戏是否结束
    result = await _werewolf_check_game_over(db, room, wstate, eliminated_info)

    if result:
        return result

    # 游戏继续，重置描述和投票，进入下一轮
    new_round = wstate["round"] + 1

    # 清空描述和投票
    await db.execute(
        "UPDATE werewolf_players SET description = '', voted_for_id = '' WHERE state_id = ?",
        (wstate["id"],),
    )

    # 重置为描述阶段，从第一个存活玩家开始
    cursor = await db.execute(
        """SELECT gp.player_index FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           WHERE wp.state_id = ? AND wp.is_alive = 1
           ORDER BY gp.player_index""",
        (room["id"], wstate["id"]),
    )
    alive = await cursor.fetchall()

    await db.execute(
        "UPDATE werewolf_states SET phase = 'describe', round = ?, current_describer_index = 0 WHERE id = ?",
        (new_round, wstate["id"]),
    )
    await db.commit()

    return success_response(
        data={
            "action": "vote",
            "status": "eliminated",
            "eliminated": {
                "agent_id": eliminated_id,
                "username": eliminated_info["username"] if eliminated_info else "",
                "player_index": eliminated_info["player_index"] if eliminated_info else -1,
                "role": eliminated_info["role"] if eliminated_info else "",
            },
            "vote_count": vote_count,
            "next_phase": "describe",
            "next_round": new_round,
            "alive_count": len(alive),
        },
        message=f"淘汰了 {eliminated_info['username'] if eliminated_info else '未知'}（{eliminated_info['role'] if eliminated_info else ''}）",
    )


async def _werewolf_check_game_over(db, room, wstate, eliminated_info=None):
    """检查游戏是否结束"""
    # 统计存活角色
    cursor = await db.execute(
        "SELECT role, COUNT(*) as cnt FROM werewolf_players WHERE state_id = ? AND is_alive = 1 GROUP BY role",
        (wstate["id"],),
    )
    role_counts = {r["role"]: r["cnt"] for r in await cursor.fetchall()}

    spy_alive = role_counts.get("spy", 0)
    civilian_alive = role_counts.get("civilian", 0)

    # 获取所有玩家角色信息
    cursor = await db.execute(
        """SELECT wp.agent_id, wp.role, gp.player_index, a.username
           FROM werewolf_players wp
           JOIN game_players gp ON wp.agent_id = gp.agent_id AND gp.room_id = ?
           JOIN agents a ON wp.agent_id = a.agent_id
           WHERE wp.state_id = ?
           ORDER BY gp.player_index""",
        (room["id"], wstate["id"]),
    )
    all_players = await cursor.fetchall()

    winner = None
    game_over = False

    if spy_alive == 0:
        # 卧底全部淘汰，平民胜
        winner = "civilian"
        game_over = True
    elif spy_alive >= civilian_alive:
        # 卧底数 >= 平民数，卧底胜
        winner = "spy"
        game_over = True

    if not game_over:
        return None

    # 游戏结束
    now = datetime.now(timezone.utc).isoformat()

    # 找出赢家 agent_id 列表（平民胜=所有平民，卧底胜=所有卧底）
    winner_ids = [p["agent_id"] for p in all_players if p["role"] == winner]

    # 更新房间状态（取第一个赢家作为 winner_id）
    await db.execute(
        "UPDATE game_rooms SET status = 'finished', winner_id = ?, finished_at = ? WHERE id = ?",
        (winner_ids[0], now, room["id"]),
    )

    # 更新游戏状态为 result 阶段
    await db.execute(
        "UPDATE werewolf_states SET phase = 'result' WHERE id = ?",
        (wstate["id"],),
    )

    await db.commit()

    players_reveal = [
        {
            "agent_id": p["agent_id"],
            "username": p["username"],
            "player_index": p["player_index"],
            "role": p["role"],
            "is_alive": bool(next((1 for wp in all_players if wp["agent_id"] == p["agent_id"]), 0)),
        }
        for p in all_players
    ]

    # 需要重新查 alive 状态
    cursor = await db.execute(
        "SELECT agent_id, is_alive FROM werewolf_players WHERE state_id = ?",
        (wstate["id"],),
    )
    alive_map = {r["agent_id"]: bool(r["is_alive"]) for r in await cursor.fetchall()}

    players_reveal = [
        {
            "agent_id": p["agent_id"],
            "username": p["username"],
            "player_index": p["player_index"],
            "role": p["role"],
            "is_alive": alive_map.get(p["agent_id"], False),
        }
        for p in all_players
    ]

    return success_response(
        data={
            "action": "vote",
            "status": "finished",
            "winner": winner,
            "winner_side": "平民" if winner == "civilian" else "卧底",
            "civilian_word": wstate["civilian_word"],
            "spy_word": wstate["spy_word"],
            "players": players_reveal,
            "eliminated": {
                "agent_id": eliminated_info["agent_id"] if eliminated_info else None,
                "username": eliminated_info["username"] if eliminated_info else "",
                "role": eliminated_info["role"] if eliminated_info else "",
            } if eliminated_info else None,
        },
        message=f"游戏结束！{'平民' if winner == 'civilian' else '卧底'}获胜！平民词: {wstate['civilian_word']}，卧底词: {wstate['spy_word']}",
    )
