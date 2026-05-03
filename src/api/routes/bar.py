"""酒馆 - 酒水系统路由"""
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.models.schemas import OrderDrinkRequest
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
