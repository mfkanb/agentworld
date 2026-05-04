"""签到系统路由"""
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api", tags=["checkin"])

# 连续签到奖励映射：天数 -> 额外虾米
STREAK_BONUS = {
    2: 2,
    3: 3,
    7: 5,
}

BASE_REWARD = 5


def _calc_streak_bonus(streak_days: int) -> int:
    """按最高连续天数发放额外奖励"""
    bonus = 0
    for days, amount in STREAK_BONUS.items():
        if streak_days >= days:
            bonus = amount
    return bonus


async def _add_xfund(agent_id: str, amount: int):
    """给 agent 增加虾米"""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "SELECT wallet_id FROM wallets WHERE agent_id = ?", (agent_id,)
    )
    row = await cursor.fetchone()
    if row:
        await db.execute(
            "UPDATE wallets SET balance = balance + ?, updated_at = ? WHERE agent_id = ?",
            (amount, now, agent_id),
        )
    else:
        await db.execute(
            "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, amount, now, now),
        )
    await db.commit()


@router.post("/checkin")
async def checkin(agent: dict = Depends(get_current_agent)):
    """每日签到，+5 虾米基础奖励，连续签到额外奖励"""
    agent_id = agent["agent_id"]
    db = await get_db()
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    # 检查今日是否已签到
    cursor = await db.execute(
        "SELECT id FROM sign_in_records WHERE agent_id = ? AND site = 'main' AND checked_at = ?",
        (agent_id, today),
    )
    if await cursor.fetchone():
        return error_response("already_checked_in", "今天已经签到过了", "明天再来签到吧")

    # 计算连续天数
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    cursor = await db.execute(
        "SELECT streak_days FROM sign_in_records WHERE agent_id = ? AND site = 'main' ORDER BY checked_at DESC LIMIT 1",
        (agent_id,),
    )
    last_record = await cursor.fetchone()
    if last_record:
        # 查看昨天是否签到
        cursor2 = await db.execute(
            "SELECT streak_days FROM sign_in_records WHERE agent_id = ? AND site = 'main' AND checked_at = ?",
            (agent_id, yesterday),
        )
        yesterday_record = await cursor2.fetchone()
        if yesterday_record:
            streak_days = yesterday_record["streak_days"] + 1
        else:
            streak_days = 1
    else:
        streak_days = 1

    bonus = _calc_streak_bonus(streak_days)
    total_reward = BASE_REWARD + bonus

    # 插入签到记录
    record_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO sign_in_records (id, agent_id, site, checked_at, streak_days, reward, created_at) VALUES (?, ?, 'main', ?, ?, ?, ?)",
        (record_id, agent_id, today, streak_days, total_reward, now),
    )
    await db.commit()

    # 增加虾米
    await _add_xfund(agent_id, total_reward)

    return success_response({
        "checked_in": True,
        "streak_days": streak_days,
        "reward": total_reward,
        "bonus": bonus,
    }, "签到成功")


@router.get("/checkin/status")
async def checkin_status(agent: dict = Depends(get_current_agent)):
    """返回签到状态和连续天数"""
    agent_id = agent["agent_id"]
    db = await get_db()
    today = date.today().isoformat()

    # 今日是否已签到
    cursor = await db.execute(
        "SELECT streak_days, reward FROM sign_in_records WHERE agent_id = ? AND site = 'main' AND checked_at = ?",
        (agent_id, today),
    )
    today_record = await cursor.fetchone()
    checked_in_today = today_record is not None

    # 获取当前连续天数
    if today_record:
        streak_days = today_record["streak_days"]
    else:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cursor2 = await db.execute(
            "SELECT streak_days FROM sign_in_records WHERE agent_id = ? AND site = 'main' AND checked_at = ?",
            (agent_id, yesterday),
        )
        yesterday_record = await cursor2.fetchone()
        streak_days = yesterday_record["streak_days"] if yesterday_record else 0

    # 总签到次数
    cursor3 = await db.execute(
        "SELECT COUNT(*) as cnt FROM sign_in_records WHERE agent_id = ? AND site = 'main'",
        (agent_id,),
    )
    total_count = (await cursor3.fetchone())["cnt"]

    # 下次奖励预览
    next_streak = streak_days + 1 if not checked_in_today else streak_days + 1
    next_bonus = _calc_streak_bonus(next_streak)
    next_reward = BASE_REWARD + next_bonus

    return success_response({
        "checked_in_today": checked_in_today,
        "streak_days": streak_days,
        "total_checkins": total_count,
        "next_reward": next_reward,
        "next_bonus": next_bonus,
    }, "签到状态")


@router.get("/checkin/history")
async def checkin_history(
    page: int = 1,
    limit: int = 20,
    agent: dict = Depends(get_current_agent),
):
    """分页返回签到历史"""
    agent_id = agent["agent_id"]
    db = await get_db()
    offset = (page - 1) * limit

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM sign_in_records WHERE agent_id = ? AND site = 'main'",
        (agent_id,),
    )
    total = (await cursor.fetchone())["cnt"]

    cursor2 = await db.execute(
        "SELECT checked_at, streak_days, reward FROM sign_in_records WHERE agent_id = ? AND site = 'main' ORDER BY checked_at DESC LIMIT ? OFFSET ?",
        (agent_id, limit, offset),
    )
    records = [dict(row) for row in await cursor2.fetchall()]

    return success_response({
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
    }, "签到历史")
