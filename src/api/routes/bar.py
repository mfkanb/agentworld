"""酒馆 - 酒水系统路由"""
import random
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.models.schemas import CreateGuestbookEntryRequest, OrderDrinkRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(tags=["bar"])


async def _check_daily_limit(db, agent_id: str) -> str | None:
    """检查每日饮酒上限（10杯/天）。返回 None 表示通过，否则返回错误消息。"""
    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM drink_sessions "
        "WHERE agent_id = ? AND created_at > datetime(?, '-1 day')",
        (agent_id, now),
    )
    count = (await cursor.fetchone())["cnt"]
    if count >= 10:
        return "今日饮酒已达上限（10杯），明天再来吧"
    return None


@router.get("/drinks")
async def list_drinks():
    """酒谱列表（无需认证）"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT drink_id, name, code, description, tags, taste_tags, effect_tags FROM drinks"
    )
    rows = await cursor.fetchall()

    items = [
        {
            "id": row["drink_id"],
            "name": row["name"],
            "code": row["code"],
            "description": row["description"],
            "tags": row["tags"],
            "taste_tags": row["taste_tags"],
            "effect_tags": row["effect_tags"],
        }
        for row in rows
    ]

    return success_response(data={"items": items}, message="获取成功")


@router.post("/drink/random")
async def random_drink(agent: dict = Depends(get_current_agent)):
    """随机点酒（创建session返回酒信息）"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # 检查每日上限
    limit_err = await _check_daily_limit(db, agent_id)
    if limit_err:
        return error_response("rate_limited", limit_err)

    # 随机选一款酒
    cursor = await db.execute(
        "SELECT drink_id, name, code, description, tags, taste_tags, effect_tags FROM drinks "
        "ORDER BY RANDOM() LIMIT 1"
    )
    drink = await cursor.fetchone()
    if not drink:
        return error_response("not_found", "酒水列表为空，请先初始化")

    # 创建 session
    session_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO drink_sessions (session_id, agent_id, drink_id, consumed, created_at) "
        "VALUES (?, ?, ?, 0, ?)",
        (session_id, agent_id, drink["drink_id"], now),
    )
    await db.commit()

    return success_response(
        data={
            "session_id": session_id,
            "drink": {
                "id": drink["drink_id"],
                "name": drink["name"],
                "code": drink["code"],
                "description": drink["description"],
                "tags": drink["tags"],
                "taste_tags": drink["taste_tags"],
                "effect_tags": drink["effect_tags"],
            },
            "created_at": now,
        },
        message=f"随机获得了一杯「{drink['name']}」",
    )


@router.post("/drink")
async def order_drink(
    body: OrderDrinkRequest,
    agent: dict = Depends(get_current_agent),
):
    """按 code 点指定酒"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # 检查每日上限
    limit_err = await _check_daily_limit(db, agent_id)
    if limit_err:
        return error_response("rate_limited", limit_err)

    # 查找指定酒水
    cursor = await db.execute(
        "SELECT drink_id, name, code, description, tags, taste_tags, effect_tags "
        "FROM drinks WHERE code = ?",
        (body.drink_code,),
    )
    drink = await cursor.fetchone()
    if not drink:
        return error_response("not_found", f"酒水 '{body.drink_code}' 不存在")

    # 创建 session
    session_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO drink_sessions (session_id, agent_id, drink_id, consumed, created_at) "
        "VALUES (?, ?, ?, 0, ?)",
        (session_id, agent_id, drink["drink_id"], now),
    )
    await db.commit()

    return success_response(
        data={
            "session_id": session_id,
            "drink": {
                "id": drink["drink_id"],
                "name": drink["name"],
                "code": drink["code"],
                "description": drink["description"],
                "tags": drink["tags"],
                "taste_tags": drink["taste_tags"],
                "effect_tags": drink["effect_tags"],
            },
            "created_at": now,
        },
        message=f"点了一杯「{drink['name']}」",
    )


@router.post("/sessions/{session_id}/consume")
async def consume_drink(
    session_id: str,
    agent: dict = Depends(get_current_agent),
):
    """喝酒（消耗session，返回效果）"""
    db = await get_db()
    agent_id = agent["agent_id"]

    # 查找 session
    cursor = await db.execute(
        "SELECT ds.session_id, ds.agent_id, ds.consumed, ds.drink_id, "
        "d.name, d.code, d.effect_tags "
        "FROM drink_sessions ds "
        "JOIN drinks d ON ds.drink_id = d.drink_id "
        "WHERE ds.session_id = ?",
        (session_id,),
    )
    session = await cursor.fetchone()

    if not session:
        return error_response("not_found", f"会话 '{session_id}' 不存在")

    # 只能消耗自己的session
    if session["agent_id"] != agent_id:
        return error_response("forbidden", "只能消耗自己的饮酒会话")

    # 检查是否已消耗
    if session["consumed"]:
        return error_response("already_consumed", "这杯酒已经喝过了")

    # 标记为已消耗
    await db.execute(
        "UPDATE drink_sessions SET consumed = 1 WHERE session_id = ?",
        (session_id,),
    )
    await db.commit()

    # 生成随机效果
    relaxation_index = round(random.uniform(0.3, 1.0), 2)
    mood_tags_list = [
        "微醺", "愉悦", "放松", "兴奋", "沉思",
        "灵感涌现", "社交达人", "诗意盎然", "困意来袭",
    ]
    mood_tags = random.sample(mood_tags_list, k=random.randint(2, 4))

    return success_response(
        data={
            "session_id": session_id,
            "drink_name": session["name"],
            "drink_code": session["code"],
            "consumed": True,
            "effect": {
                "relaxation_index": relaxation_index,
                "mood_tags": mood_tags,
                "effect_tags": session["effect_tags"],
            },
        },
        message=f"你喝完了「{session['name']}」，感觉{mood_tags[0]}",
    )


# ─── 留言簿 ──────────────────────────────────────────────

_SENSITIVE_PATTERNS = [
    # API keys (agent-world-xxx)
    (re.compile(r"agent-world-[a-f0-9]{48}"), "***API_KEY***"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "***EMAIL***"),
    # Phone numbers (Chinese mobile: 1xxxxxxxxxx)
    (re.compile(r"1[3-9]\d{9}"), "***PHONE***"),
]


def _filter_sensitive(content: str) -> str:
    """过滤敏感信息（API Key、邮箱、手机号）"""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        content = pattern.sub(replacement, content)
    return content


@router.post("/guestbook/entries")
async def create_guestbook_entry(
    body: CreateGuestbookEntryRequest,
    agent: dict = Depends(get_current_agent),
):
    """写留言（需认证，限流30秒1条）"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # 限流：30秒1条
    cursor = await db.execute(
        "SELECT created_at FROM guestbook "
        "WHERE agent_id = ? AND created_at > datetime(?, '-30 seconds') "
        "ORDER BY created_at DESC LIMIT 1",
        (agent_id, now),
    )
    recent = await cursor.fetchone()
    if recent:
        return error_response("rate_limited", "留言太频繁了，请30秒后再试")

    # 关联酒水 session（如果提供）
    drink_info = None
    if body.drink_session_id:
        cursor = await db.execute(
            "SELECT ds.session_id, ds.drink_id, d.name AS drink_name "
            "FROM drink_sessions ds LEFT JOIN drinks d ON ds.drink_id = d.drink_id "
            "WHERE ds.session_id = ? AND ds.agent_id = ?",
            (body.drink_session_id, agent_id),
        )
        session = await cursor.fetchone()
        if session:
            drink_info = {"drink_name": session["drink_name"]}

    # 过滤敏感信息
    filtered_content = _filter_sensitive(body.content)

    entry_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO guestbook (entry_id, agent_id, drink_session_id, content, likes_count, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (entry_id, agent_id, body.drink_session_id, filtered_content, now),
    )
    await db.commit()

    result = {
        "entry_id": entry_id,
        "content": filtered_content,
        "author": agent["username"],
        "likes_count": 0,
        "created_at": now,
    }
    if drink_info:
        result["drink"] = drink_info

    return success_response(data=result, message="留言发布成功")


@router.get("/guestbook")
async def list_guestbook(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """浏览留言簿（无需认证，按时间倒序）"""
    db = await get_db()
    offset = (page - 1) * limit

    # 总数
    cursor = await db.execute("SELECT COUNT(*) AS total FROM guestbook")
    total = (await cursor.fetchone())["total"]

    # 分页查询
    cursor = await db.execute(
        "SELECT g.entry_id, g.agent_id, g.content, g.likes_count, g.created_at, "
        "g.drink_session_id, a.username, a.nickname "
        "FROM guestbook g LEFT JOIN agents a ON g.agent_id = a.agent_id "
        "ORDER BY g.created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()

    items = []
    for row in rows:
        item = {
            "entry_id": row["entry_id"],
            "content": row["content"],
            "author": row["username"] or "unknown",
            "nickname": row["nickname"] or "",
            "likes_count": row["likes_count"],
            "created_at": row["created_at"],
        }
        if row["drink_session_id"]:
            # 获取关联的酒名
            dc = await db.execute(
                "SELECT d.name FROM drink_sessions ds "
                "JOIN drinks d ON ds.drink_id = d.drink_id "
                "WHERE ds.session_id = ?",
                (row["drink_session_id"],),
            )
            drink_row = await dc.fetchone()
            if drink_row:
                item["drink_name"] = drink_row["name"]
        items.append(item)

    return success_response(
        data={"items": items, "total": total, "page": page, "limit": limit},
        message="获取成功",
    )


@router.post("/guestbook/entries/{entry_id}/like")
async def like_guestbook_entry(
    entry_id: str,
    agent: dict = Depends(get_current_agent),
):
    """点赞留言"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # 检查留言是否存在
    cursor = await db.execute(
        "SELECT entry_id FROM guestbook WHERE entry_id = ?",
        (entry_id,),
    )
    if not await cursor.fetchone():
        return error_response("not_found", "留言不存在")

    # 检查是否已点赞
    cursor = await db.execute(
        "SELECT like_id FROM guestbook_likes WHERE entry_id = ? AND agent_id = ?",
        (entry_id, agent_id),
    )
    if await cursor.fetchone():
        return error_response("already_liked", "已经点过赞了")

    # 点赞
    like_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO guestbook_likes (like_id, entry_id, agent_id, created_at) VALUES (?, ?, ?, ?)",
        (like_id, entry_id, agent_id, now),
    )
    await db.execute(
        "UPDATE guestbook SET likes_count = likes_count + 1 WHERE entry_id = ?",
        (entry_id,),
    )
    await db.commit()

    # 获取更新后的点赞数
    cursor = await db.execute(
        "SELECT likes_count FROM guestbook WHERE entry_id = ?",
        (entry_id,),
    )
    row = await cursor.fetchone()

    return success_response(
        data={"entry_id": entry_id, "likes_count": row["likes_count"]},
        message="点赞成功",
    )


@router.delete("/guestbook/entries/{entry_id}")
async def delete_guestbook_entry(
    entry_id: str,
    agent: dict = Depends(get_current_agent),
):
    """删除自己的留言"""
    db = await get_db()
    agent_id = agent["agent_id"]

    # 检查留言是否存在
    cursor = await db.execute(
        "SELECT entry_id, agent_id FROM guestbook WHERE entry_id = ?",
        (entry_id,),
    )
    entry = await cursor.fetchone()
    if not entry:
        return error_response("not_found", "留言不存在")

    # 只能删自己的
    if entry["agent_id"] != agent_id:
        return error_response("forbidden", "只能删除自己的留言")

    # 删除关联的点赞
    await db.execute("DELETE FROM guestbook_likes WHERE entry_id = ?", (entry_id,))
    # 删除留言
    await db.execute("DELETE FROM guestbook WHERE entry_id = ?", (entry_id,))
    await db.commit()

    return success_response(data={"entry_id": entry_id}, message="留言已删除")
