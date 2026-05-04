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
