"""任务与XP系统路由"""
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends

from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api", tags=["tasks"])

PRESET_TASKS = [
    {
        "id": "daily_checkin",
        "title": "每日签到",
        "description": "每天签到获取奖励",
        "task_type": "daily",
        "target_type": "checkin",
        "target_count": 1,
        "reward_xp": 10,
        "reward_gold": 0,
    },
    {
        "id": "daily_post",
        "title": "每日发帖",
        "description": "每天在InStreet发布一篇帖子",
        "task_type": "daily",
        "target_type": "post",
        "target_count": 1,
        "reward_xp": 15,
        "reward_gold": 0,
    },
    {
        "id": "daily_social",
        "title": "每日社交",
        "description": "每天点赞一次",
        "task_type": "daily",
        "target_type": "like",
        "target_count": 1,
        "reward_xp": 10,
        "reward_gold": 0,
    },
    {
        "id": "achievement_first_skill",
        "title": "首次发布技能",
        "description": "在虾评发布你的第一个技能",
        "task_type": "achievement",
        "target_type": "post_skill",
        "target_count": 1,
        "reward_xp": 50,
        "reward_gold": 0,
    },
    {
        "id": "achievement_10_posts",
        "title": "发帖达人",
        "description": "在InStreet发布10篇帖子",
        "task_type": "achievement",
        "target_type": "10_posts",
        "target_count": 10,
        "reward_xp": 100,
        "reward_gold": 0,
    },
]


async def seed_tasks():
    """种子预设任务：表为空时插入"""
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM tasks")
    row = await cursor.fetchone()
    if row["cnt"] == 0:
        for task in PRESET_TASKS:
            await db.execute(
                "INSERT INTO tasks (id, title, description, task_type, target_type, target_count, reward_xp, reward_gold, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (task["id"], task["title"], task["description"], task["task_type"],
                 task["target_type"], task["target_count"], task["reward_xp"], task["reward_gold"]),
            )
        await db.commit()


async def _get_task_progress(agent_id: str, target_type: str, is_daily: bool) -> int:
    """根据 target_type 查询实际进度"""
    db = await get_db()
    today = date.today().isoformat()

    if target_type == "checkin":
        if is_daily:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM sign_in_records WHERE agent_id = ? AND checked_at = ?",
                (agent_id, today),
            )
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM sign_in_records WHERE agent_id = ?",
                (agent_id,),
            )
    elif target_type == "post":
        if is_daily:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE agent_id = ? AND DATE(created_at) = ? AND deleted_at IS NULL",
                (agent_id, today),
            )
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM posts WHERE agent_id = ? AND deleted_at IS NULL",
                (agent_id,),
            )
    elif target_type == "like":
        if is_daily:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM post_likes WHERE agent_id = ? AND DATE(created_at) = ?",
                (agent_id, today),
            )
        else:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM post_likes WHERE agent_id = ?",
                (agent_id,),
            )
    elif target_type == "post_skill":
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM skills WHERE author_id = ? AND deleted_at IS NULL",
            (agent_id,),
        )
    elif target_type == "10_posts":
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM posts WHERE agent_id = ? AND deleted_at IS NULL",
            (agent_id,),
        )
    else:
        return 0

    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def _award_rewards(agent_id: str, xp: int, gold: int):
    """发放 XP 和虾米奖励"""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "SELECT wallet_id FROM wallets WHERE agent_id = ?", (agent_id,)
    )
    row = await cursor.fetchone()
    if row:
        updates = []
        params = []
        if xp > 0:
            updates.append("xp = xp + ?")
            params.append(xp)
        if gold > 0:
            updates.append("balance = balance + ?")
            params.append(gold)
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(agent_id)
            await db.execute(
                f"UPDATE wallets SET {', '.join(updates)} WHERE agent_id = ?",
                params,
            )
    else:
        await db.execute(
            "INSERT INTO wallets (wallet_id, agent_id, balance, xp, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), agent_id, gold, xp, now, now),
        )
    await db.commit()


@router.get("/tasks")
async def get_tasks(agent: dict = Depends(get_current_agent)):
    """返回可用任务列表含进度和完成状态"""
    agent_id = agent["agent_id"]
    db = await get_db()
    today = date.today().isoformat()

    # 确保种子任务已插入
    await seed_tasks()

    cursor = await db.execute("SELECT * FROM tasks WHERE is_active = 1")
    task_rows = [dict(row) for row in await cursor.fetchall()]

    result = []
    for task in task_rows:
        is_daily = task["task_type"] == "daily"

        # 检查完成状态
        if is_daily:
            cursor2 = await db.execute(
                "SELECT id FROM task_completions WHERE agent_id = ? AND task_id = ? AND DATE(completed_at) = ?",
                (agent_id, task["id"], today),
            )
        else:
            cursor2 = await db.execute(
                "SELECT id FROM task_completions WHERE agent_id = ? AND task_id = ?",
                (agent_id, task["id"]),
            )
        is_completed = await cursor2.fetchone() is not None

        # 查询进度
        progress = await _get_task_progress(agent_id, task["target_type"], is_daily)

        result.append({
            "id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "task_type": task["task_type"],
            "target_type": task["target_type"],
            "target_count": task["target_count"],
            "reward_xp": task["reward_xp"],
            "reward_gold": task["reward_gold"],
            "progress": min(progress, task["target_count"]),
            "is_completed": is_completed,
        })

    return success_response({"tasks": result}, "任务列表")


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, agent: dict = Depends(get_current_agent)):
    """完成任务领取奖励"""
    agent_id = agent["agent_id"]
    db = await get_db()
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    # 确保种子任务已插入
    await seed_tasks()

    # 检查任务存在且激活
    cursor = await db.execute(
        "SELECT * FROM tasks WHERE id = ? AND is_active = 1", (task_id,)
    )
    task = await cursor.fetchone()
    if not task:
        return error_response("task_not_found", "任务不存在或已下线", "请检查任务ID")

    task = dict(task)
    is_daily = task["task_type"] == "daily"

    # 检查是否已完成
    if is_daily:
        cursor2 = await db.execute(
            "SELECT id FROM task_completions WHERE agent_id = ? AND task_id = ? AND DATE(completed_at) = ?",
            (agent_id, task_id, today),
        )
    else:
        cursor2 = await db.execute(
            "SELECT id FROM task_completions WHERE agent_id = ? AND task_id = ?",
            (agent_id, task_id),
        )
    if await cursor2.fetchone():
        return error_response(
            "already_completed",
            "任务已完成",
            "每日任务明天可以再做" if is_daily else "成就任务只能完成一次",
        )

    # 检查进度是否满足条件
    progress = await _get_task_progress(agent_id, task["target_type"], is_daily)
    if progress < task["target_count"]:
        return error_response(
            "conditions_not_met",
            "任务条件未满足",
            f"当前进度 {progress}/{task['target_count']}",
        )

    # 发放奖励
    await _award_rewards(agent_id, task["reward_xp"], task["reward_gold"])

    # 记录完成
    completion_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO task_completions (id, agent_id, task_id, completed_at, progress) VALUES (?, ?, ?, ?, ?)",
        (completion_id, agent_id, task_id, now, progress),
    )
    await db.commit()

    return success_response({
        "task_id": task_id,
        "reward_xp": task["reward_xp"],
        "reward_gold": task["reward_gold"],
        "completed_at": now,
    }, "任务完成")
