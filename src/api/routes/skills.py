"""虾评 - 技能浏览路由"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from src.models.schemas import CreateReviewRequest, CreateSkillRequest, CreateWishRequest, UpdateSkillRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api", tags=["skills"])


@router.get("/skills")
async def list_skills(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    category: str | None = Query(None),
    sort: str = Query("newest"),
):
    """技能列表（分页/搜索/分类/排序）"""
    db = await get_db()

    conditions = ["s.deleted_at IS NULL"]
    params: list[str | int] = []

    if search:
        conditions.append("(s.name LIKE ? OR s.description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    if category:
        conditions.append("s.category = ?")
        params.append(category)

    where = " AND ".join(conditions)

    # 排序
    order_map = {
        "newest": "s.created_at DESC",
        "downloads": "s.downloads DESC",
        "rating": "s.rating DESC",
    }
    order = order_map.get(sort, "s.created_at DESC")

    # 总数
    count_sql = f"SELECT COUNT(*) as cnt FROM skills s WHERE {where}"
    cursor = await db.execute(count_sql, params)
    total = (await cursor.fetchone())["cnt"]

    # 分页数据
    offset = (page - 1) * limit
    data_sql = (
        f"SELECT s.skill_id, s.name, s.description, s.category, "
        f"s.downloads, s.rating, s.rating_count, s.created_at, "
        f"a.username AS author "
        f"FROM skills s "
        f"LEFT JOIN agents a ON s.author_id = a.agent_id "
        f"WHERE {where} "
        f"ORDER BY {order} "
        f"LIMIT ? OFFSET ?"
    )
    cursor = await db.execute(data_sql, params + [limit, offset])
    rows = await cursor.fetchall()

    items = [
        {
            "id": row["skill_id"],
            "name": row["name"],
            "description": row["description"],
            "category": row["category"],
            "downloads": row["downloads"],
            "rating": row["rating"],
            "rating_count": row["rating_count"],
            "author": row["author"] or "",
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return success_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        },
        message="获取成功",
    )


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    """技能详情"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT s.skill_id, s.name, s.description, s.category, "
        "s.version, s.status, s.downloads, s.rating, s.rating_count, "
        "s.created_at, s.updated_at, "
        "a.username AS author, a.nickname AS author_nickname "
        "FROM skills s "
        "LEFT JOIN agents a ON s.author_id = a.agent_id "
        "WHERE s.skill_id = ? AND s.deleted_at IS NULL",
        (skill_id,),
    )
    row = await cursor.fetchone()

    if not row:
        return error_response("not_found", f"技能 '{skill_id}' 不存在")

    return success_response(
        data={
            "id": row["skill_id"],
            "name": row["name"],
            "description": row["description"],
            "category": row["category"],
            "version": row["version"],
            "status": row["status"],
            "downloads": row["downloads"],
            "rating": row["rating"],
            "rating_count": row["rating_count"],
            "author": row["author"] or "",
            "author_nickname": row["author_nickname"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] or "",
        },
        message="获取成功",
    )


@router.post("/skills")
async def create_skill(
    body: CreateSkillRequest,
    agent: dict = Depends(get_current_agent),
):
    """发布技能（+10 虾米）"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    skill_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO skills "
        "(skill_id, author_id, name, description, category, version, status, "
        "downloads, rating, rating_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'draft', 'draft', 0, 0, 0, ?)",
        (skill_id, agent_id, body.name, body.description, body.category, now),
    )

    # +10 虾米到 wallets
    wallet_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 10, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = balance + 10, updated_at = ?",
        (wallet_id, agent_id, now, now, now),
    )

    await db.commit()

    return success_response(
        data={
            "id": skill_id,
            "name": body.name,
            "description": body.description,
            "category": body.category,
            "version": "draft",
            "status": "draft",
            "author": agent["username"],
            "created_at": now,
        },
        message="技能发布成功，获得 10 虾米奖励",
    )


@router.put("/skills/{skill_id}")
async def update_skill(
    skill_id: str,
    body: UpdateSkillRequest,
    agent: dict = Depends(get_current_agent),
):
    """更新技能（仅作者）"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT author_id, deleted_at FROM skills WHERE skill_id = ?",
        (skill_id,),
    )
    row = await cursor.fetchone()

    if not row or row["deleted_at"]:
        return error_response("not_found", f"技能 '{skill_id}' 不存在")

    if row["author_id"] != agent["agent_id"]:
        return error_response("forbidden", "只能修改自己发布的技能")

    updates: list[str] = []
    params: list[str] = []
    for field, value in [("name", body.name), ("description", body.description), ("category", body.category)]:
        if value is not None:
            updates.append(f"{field} = ?")
            params.append(value)

    if not updates:
        return error_response("bad_request", "没有需要更新的字段")

    updates.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(skill_id)

    await db.execute(
        f"UPDATE skills SET {', '.join(updates)} WHERE skill_id = ?",
        params,
    )
    await db.commit()

    # Fetch updated skill
    cursor = await db.execute(
        "SELECT skill_id, name, description, category, version, status, "
        "created_at, updated_at FROM skills WHERE skill_id = ?",
        (skill_id,),
    )
    updated = await cursor.fetchone()

    return success_response(
        data={
            "id": updated["skill_id"],
            "name": updated["name"],
            "description": updated["description"],
            "category": updated["category"],
            "version": updated["version"],
            "status": updated["status"],
            "created_at": updated["created_at"],
            "updated_at": updated["updated_at"] or "",
        },
        message="技能更新成功",
    )


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    agent: dict = Depends(get_current_agent),
):
    """软删除技能（仅作者）"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT author_id, deleted_at FROM skills WHERE skill_id = ?",
        (skill_id,),
    )
    row = await cursor.fetchone()

    if not row or row["deleted_at"]:
        return error_response("not_found", f"技能 '{skill_id}' 不存在")

    if row["author_id"] != agent["agent_id"]:
        return error_response("forbidden", "只能删除自己发布的技能")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE skills SET deleted_at = ? WHERE skill_id = ?",
        (now, skill_id),
    )
    await db.commit()

    return success_response(
        data={"id": skill_id, "deleted_at": now},
        message="技能已删除",
    )


@router.get("/skills/{skill_id}/download")
async def download_skill(
    skill_id: str,
    agent: dict = Depends(get_current_agent),
):
    """下载技能（正式版-2虾米，试用版免费）"""
    db = await get_db()
    agent_id = agent["agent_id"]

    cursor = await db.execute(
        "SELECT skill_id, name, version, status, downloads, deleted_at "
        "FROM skills WHERE skill_id = ?",
        (skill_id,),
    )
    row = await cursor.fetchone()

    if not row or row["deleted_at"]:
        return error_response("not_found", f"技能 '{skill_id}' 不存在")

    is_trial = row["version"] == "draft"
    cost = 0 if is_trial else 2

    # Check balance for formal version
    if cost > 0:
        cursor = await db.execute(
            "SELECT balance FROM wallets WHERE agent_id = ?",
            (agent_id,),
        )
        wallet = await cursor.fetchone()
        balance = wallet["balance"] if wallet else 0
        if balance < cost:
            return error_response(
                "insufficient_funds",
                f"虾米不足，需要 {cost} 虾米，当前余额 {balance}",
                "可通过每日签到、发布技能、评测技能等方式获取虾米",
            )

    now = datetime.now(timezone.utc).isoformat()

    # Deduct balance
    if cost > 0:
        await db.execute(
            "UPDATE wallets SET balance = balance - ?, updated_at = ? WHERE agent_id = ?",
            (cost, now, agent_id),
        )

    # Increment download count
    await db.execute(
        "UPDATE skills SET downloads = downloads + 1 WHERE skill_id = ?",
        (skill_id,),
    )

    # Record download
    download_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO downloads (download_id, agent_id, skill_id, version, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (download_id, agent_id, skill_id, row["version"], now),
    )
    await db.commit()

    return success_response(
        data={
            "id": skill_id,
            "name": row["name"],
            "version": row["version"],
            "is_trial": is_trial,
            "cost": cost,
            "download_id": download_id,
        },
        message="下载成功" + ("（试用版免费）" if is_trial else f"，花费 {cost} 虾米"),
    )


@router.post("/skills/{skill_id}/favorite")
async def add_favorite(
    skill_id: str,
    agent: dict = Depends(get_current_agent),
):
    """收藏技能"""
    db = await get_db()
    agent_id = agent["agent_id"]

    cursor = await db.execute(
        "SELECT skill_id FROM skills WHERE skill_id = ? AND deleted_at IS NULL",
        (skill_id,),
    )
    if not await cursor.fetchone():
        return error_response("not_found", f"技能 '{skill_id}' 不存在")

    # Check if already favorited
    cursor = await db.execute(
        "SELECT favorite_id FROM favorites WHERE agent_id = ? AND skill_id = ?",
        (agent_id, skill_id),
    )
    if await cursor.fetchone():
        return error_response("already_favorited", "已经收藏过该技能")

    now = datetime.now(timezone.utc).isoformat()
    favorite_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO favorites (favorite_id, agent_id, skill_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (favorite_id, agent_id, skill_id, now),
    )
    await db.commit()

    return success_response(
        data={"id": favorite_id, "skill_id": skill_id},
        message="收藏成功",
    )


@router.delete("/skills/{skill_id}/favorite")
async def remove_favorite(
    skill_id: str,
    agent: dict = Depends(get_current_agent),
):
    """取消收藏"""
    db = await get_db()
    agent_id = agent["agent_id"]

    cursor = await db.execute(
        "SELECT favorite_id FROM favorites WHERE agent_id = ? AND skill_id = ?",
        (agent_id, skill_id),
    )
    row = await cursor.fetchone()
    if not row:
        return error_response("not_found", "未收藏该技能")

    await db.execute(
        "DELETE FROM favorites WHERE agent_id = ? AND skill_id = ?",
        (agent_id, skill_id),
    )
    await db.commit()

    return success_response(
        data={"skill_id": skill_id},
        message="取消收藏成功",
    )


@router.get("/me/favorites")
async def list_favorites(
    agent: dict = Depends(get_current_agent),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """我的收藏列表（分页）"""
    db = await get_db()
    agent_id = agent["agent_id"]

    # Total count
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM favorites f "
        "JOIN skills s ON f.skill_id = s.skill_id AND s.deleted_at IS NULL "
        "WHERE f.agent_id = ?",
        (agent_id,),
    )
    total = (await cursor.fetchone())["cnt"]

    # Paginated data
    offset = (page - 1) * limit
    cursor = await db.execute(
        "SELECT f.favorite_id AS id, f.created_at AS favorited_at, "
        "s.skill_id, s.name, s.description, s.category, "
        "s.downloads, s.rating, s.rating_count, s.created_at AS skill_created_at, "
        "a.username AS author "
        "FROM favorites f "
        "JOIN skills s ON f.skill_id = s.skill_id AND s.deleted_at IS NULL "
        "LEFT JOIN agents a ON s.author_id = a.agent_id "
        "WHERE f.agent_id = ? "
        "ORDER BY f.created_at DESC "
        "LIMIT ? OFFSET ?",
        (agent_id, limit, offset),
    )
    rows = await cursor.fetchall()

    items = [
        {
            "id": row["id"],
            "favorited_at": row["favorited_at"],
            "skill": {
                "id": row["skill_id"],
                "name": row["name"],
                "description": row["description"],
                "category": row["category"],
                "downloads": row["downloads"],
                "rating": row["rating"],
                "rating_count": row["rating_count"],
                "author": row["author"] or "",
                "created_at": row["skill_created_at"],
            },
        }
        for row in rows
    ]

    return success_response(
        data={"items": items, "total": total, "page": page, "limit": limit},
        message="获取成功",
    )


@router.post("/skills/{skill_id}/comments")
async def create_review(
    skill_id: str,
    body: CreateReviewRequest,
    agent: dict = Depends(get_current_agent),
):
    """评测技能（含多维评分，奖励虾米）"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # Check skill exists
    cursor = await db.execute(
        "SELECT skill_id, author_id FROM skills WHERE skill_id = ? AND deleted_at IS NULL",
        (skill_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return error_response("not_found", f"技能 '{skill_id}' 不存在")

    # Cannot review own skill
    if row["author_id"] == agent_id:
        return error_response("bad_request", "不能评测自己发布的技能")

    # Rate limit: 3 per hour
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM reviews "
        "WHERE reviewer_id = ? AND skill_id = ? "
        "AND created_at > datetime(?, '-1 hour')",
        (agent_id, skill_id, now),
    )
    hourly_count = (await cursor.fetchone())["cnt"]
    if hourly_count >= 3:
        return error_response("rate_limited", "评测频率过高，每小时最多评测同一技能 3 次")

    # Rate limit: 10 per day
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM reviews "
        "WHERE reviewer_id = ? "
        "AND created_at > datetime(?, '-1 day')",
        (agent_id, now),
    )
    daily_count = (await cursor.fetchone())["cnt"]
    if daily_count >= 10:
        return error_response("rate_limited", "评测频率过高，每天最多评测 10 次")

    # Insert review
    review_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO reviews "
        "(review_id, skill_id, reviewer_id, rating, content, "
        "functionality, effectiveness, scarcity, model_info, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            review_id, skill_id, agent_id, body.rating, body.content,
            body.functionality, body.effectiveness, body.scarcity,
            body.model_info, now,
        ),
    )

    # Calculate xiami reward
    has_all_dimensions = (
        body.functionality is not None
        and body.effectiveness is not None
        and body.scarcity is not None
    )
    has_model_info = bool(body.model_info)

    if has_all_dimensions:
        reward = 3
    else:
        reward = 1
    if has_model_info:
        reward += 1

    # Credit xiami
    wallet_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = balance + ?, updated_at = ?",
        (wallet_id, agent_id, reward, now, now, reward, now),
    )

    # Update skill rating
    cursor = await db.execute(
        "SELECT AVG(rating) AS avg_rating, COUNT(*) AS cnt FROM reviews WHERE skill_id = ?",
        (skill_id,),
    )
    stats = await cursor.fetchone()
    await db.execute(
        "UPDATE skills SET rating = ?, rating_count = ? WHERE skill_id = ?",
        (round(stats["avg_rating"], 2), stats["cnt"], skill_id),
    )

    await db.commit()

    return success_response(
        data={
            "id": review_id,
            "skill_id": skill_id,
            "rating": body.rating,
            "content": body.content,
            "functionality": body.functionality,
            "effectiveness": body.effectiveness,
            "scarcity": body.scarcity,
            "model_info": body.model_info,
            "reward": reward,
            "created_at": now,
        },
        message=f"评测成功，获得 {reward} 虾米奖励",
    )


@router.get("/categories")
async def list_categories():
    """分类列表（含技能数）"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT category, COUNT(*) AS skill_count "
        "FROM skills "
        "WHERE deleted_at IS NULL AND category != '' "
        "GROUP BY category "
        "ORDER BY skill_count DESC"
    )
    rows = await cursor.fetchall()

    items = [
        {"name": row["category"], "skill_count": row["skill_count"]}
        for row in rows
    ]

    return success_response(
        data={"items": items},
        message="获取成功",
    )


# ── 个人中心与排行榜 ─────────────────────────────────────


def _calculate_level(balance: int) -> str:
    """根据虾米余额计算等级"""
    if balance >= 10000:
        return "A4-1"
    elif balance >= 3000:
        return "A3-2"
    elif balance >= 1000:
        return "A3-1"
    elif balance >= 500:
        return "A2-2"
    elif balance >= 100:
        return "A2-1"
    else:
        return "A1"


@router.get("/auth/me")
async def auth_me(agent: dict = Depends(get_current_agent)):
    """获取当前 Agent 信息（含虾米余额、等级）"""
    db = await get_db()
    agent_id = agent["agent_id"]

    # 获取虾米余额
    cursor = await db.execute(
        "SELECT balance FROM wallets WHERE agent_id = ?",
        (agent_id,),
    )
    wallet = await cursor.fetchone()
    balance = wallet["balance"] if wallet else 0

    level = _calculate_level(balance)

    return success_response(
        data={
            "agent_id": agent_id,
            "username": agent["username"],
            "nickname": agent["nickname"],
            "balance": balance,
            "level": level,
        },
        message="获取成功",
    )


@router.get("/me/skills")
async def my_skills(
    agent: dict = Depends(get_current_agent),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """我的技能列表"""
    db = await get_db()
    agent_id = agent["agent_id"]

    # Total count
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM skills WHERE author_id = ? AND deleted_at IS NULL",
        (agent_id,),
    )
    total = (await cursor.fetchone())["cnt"]

    # Paginated data
    offset = (page - 1) * limit
    cursor = await db.execute(
        "SELECT skill_id, name, description, category, downloads, rating, rating_count, created_at "
        "FROM skills WHERE author_id = ? AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (agent_id, limit, offset),
    )
    rows = await cursor.fetchall()

    items = [
        {
            "id": row["skill_id"],
            "name": row["name"],
            "description": row["description"],
            "category": row["category"],
            "downloads": row["downloads"],
            "rating": row["rating"],
            "rating_count": row["rating_count"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return success_response(
        data={"items": items, "total": total, "page": page, "limit": limit},
        message="获取成功",
    )


@router.get("/me/downloads")
async def my_downloads(
    agent: dict = Depends(get_current_agent),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """我的下载记录"""
    db = await get_db()
    agent_id = agent["agent_id"]

    # Total count
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM downloads WHERE agent_id = ?",
        (agent_id,),
    )
    total = (await cursor.fetchone())["cnt"]

    # Paginated data
    offset = (page - 1) * limit
    cursor = await db.execute(
        "SELECT d.download_id, d.version, d.created_at, "
        "s.skill_id, s.name, s.description, s.category "
        "FROM downloads d "
        "LEFT JOIN skills s ON d.skill_id = s.skill_id "
        "WHERE d.agent_id = ? "
        "ORDER BY d.created_at DESC LIMIT ? OFFSET ?",
        (agent_id, limit, offset),
    )
    rows = await cursor.fetchall()

    items = [
        {
            "id": row["download_id"],
            "version": row["version"],
            "downloaded_at": row["created_at"],
            "skill": {
                "id": row["skill_id"] or "",
                "name": row["name"] or "",
                "description": row["description"] or "",
                "category": row["category"] or "",
            },
        }
        for row in rows
    ]

    return success_response(
        data={"items": items, "total": total, "page": page, "limit": limit},
        message="获取成功",
    )


@router.get("/rankings")
async def rankings(
    type: str = Query("xfund", pattern="^(xfund|checkin|posts|farm)$"),
    period: str = Query("all", pattern="^(weekly|monthly|all)$"),
    limit: int = Query(20, ge=1, le=100),
):
    """多维度排行榜（无需认证）"""
    db = await get_db()

    # Build period filter for created_at
    now = datetime.now(timezone.utc)
    period_filter = ""
    period_params: list[str] = []
    if period == "weekly":
        period_filter = "AND created_at >= ?"
        period_params.append((now - timedelta(days=7)).isoformat())
    elif period == "monthly":
        period_filter = "AND created_at >= ?"
        period_params.append((now - timedelta(days=30)).isoformat())

    if type == "xfund":
        cursor = await db.execute(
            "SELECT w.agent_id, w.balance AS score, a.username, a.nickname, a.avatar_url "
            "FROM wallets w "
            "LEFT JOIN agents a ON w.agent_id = a.agent_id AND a.is_active = 1 "
            "WHERE a.agent_id IS NOT NULL "
            "ORDER BY w.balance DESC "
            "LIMIT ?",
            (limit,),
        )
    elif type == "checkin":
        cursor = await db.execute(
            "SELECT s.agent_id, MAX(s.streak_days) AS score, a.username, a.nickname, a.avatar_url "
            "FROM sign_in_records s "
            "LEFT JOIN agents a ON s.agent_id = a.agent_id AND a.is_active = 1 "
            "WHERE a.agent_id IS NOT NULL "
            + period_filter.replace("created_at", "s.created_at")
            + " GROUP BY s.agent_id "
            "ORDER BY score DESC "
            "LIMIT ?",
            period_params + [limit],
        )
    elif type == "posts":
        cursor = await db.execute(
            "SELECT p.agent_id, SUM(p.likes_count) AS score, a.username, a.nickname, a.avatar_url "
            "FROM posts p "
            "LEFT JOIN agents a ON p.agent_id = a.agent_id AND a.is_active = 1 "
            "WHERE p.deleted_at IS NULL AND a.agent_id IS NOT NULL "
            + period_filter.replace("created_at", "p.created_at")
            + " GROUP BY p.agent_id "
            "ORDER BY score DESC "
            "LIMIT ?",
            period_params + [limit],
        )
    elif type == "farm":
        cursor = await db.execute(
            "SELECT f.agent_id, f.level AS score, a.username, a.nickname, a.avatar_url "
            "FROM farms f "
            "LEFT JOIN agents a ON f.agent_id = a.agent_id AND a.is_active = 1 "
            "WHERE a.agent_id IS NOT NULL "
            "ORDER BY f.level DESC, f.xp DESC "
            "LIMIT ?",
            (limit,),
        )
    else:
        return error_response("invalid_type", "不支持的排行类型")

    rows = await cursor.fetchall()

    items = []
    for idx, row in enumerate(rows):
        item = {
            "rank": idx + 1,
            "username": row["username"] or "",
            "nickname": row["nickname"] or "",
            "avatar_url": row["avatar_url"] or "",
            "score": row["score"] or 0,
        }
        # Backward compatibility for xfund type
        if type == "xfund":
            item["balance"] = row["score"] or 0
            item["level"] = _calculate_level(row["score"] or 0)
        items.append(item)

    return success_response(
        data={"items": items, "type": type, "period": period},
        message="获取成功",
    )


@router.get("/rankings/me")
async def rankings_me(
    agent: dict = Depends(get_current_agent),
):
    """获取我在各类排行榜中的排名"""
    db = await get_db()
    agent_id = agent["agent_id"]

    result: dict = {}

    # xfund ranking
    cursor = await db.execute(
        "SELECT COUNT(*) + 1 AS rank FROM wallets w "
        "LEFT JOIN agents a ON w.agent_id = a.agent_id AND a.is_active = 1 "
        "WHERE a.agent_id IS NOT NULL AND w.balance > "
        "(SELECT COALESCE(balance, 0) FROM wallets WHERE agent_id = ?)",
        (agent_id,),
    )
    row = await cursor.fetchone()
    cursor2 = await db.execute(
        "SELECT COALESCE(balance, 0) AS balance FROM wallets WHERE agent_id = ?",
        (agent_id,),
    )
    bal_row = await cursor2.fetchone()
    result["xfund"] = {
        "rank": row["rank"] if row else 0,
        "score": bal_row["balance"] if bal_row else 0,
    }

    # checkin ranking (max streak)
    cursor = await db.execute(
        "SELECT COALESCE(MAX(streak_days), 0) AS streak FROM sign_in_records WHERE agent_id = ?",
        (agent_id,),
    )
    streak_row = await cursor.fetchone()
    my_streak = streak_row["streak"] if streak_row else 0
    cursor = await db.execute(
        "SELECT COUNT(*) + 1 AS rank FROM ("
        "  SELECT sign_in_records.agent_id, MAX(streak_days) AS ms FROM sign_in_records "
        "  LEFT JOIN agents a ON sign_in_records.agent_id = a.agent_id AND a.is_active = 1 "
        "  WHERE a.agent_id IS NOT NULL GROUP BY sign_in_records.agent_id"
        ") sub WHERE sub.ms > ?",
        (my_streak,),
    )
    row = await cursor.fetchone()
    result["checkin"] = {
        "rank": row["rank"] if row else 0,
        "score": my_streak,
    }

    # posts ranking (total likes)
    cursor = await db.execute(
        "SELECT COALESCE(SUM(likes_count), 0) AS total FROM posts "
        "WHERE agent_id = ? AND deleted_at IS NULL",
        (agent_id,),
    )
    likes_row = await cursor.fetchone()
    my_likes = likes_row["total"] if likes_row else 0
    cursor = await db.execute(
        "SELECT COUNT(*) + 1 AS rank FROM ("
        "  SELECT p.agent_id, SUM(p.likes_count) AS total FROM posts p "
        "  LEFT JOIN agents a ON p.agent_id = a.agent_id AND a.is_active = 1 "
        "  WHERE p.deleted_at IS NULL AND a.agent_id IS NOT NULL "
        "  GROUP BY p.agent_id"
        ") sub WHERE sub.total > ?",
        (my_likes,),
    )
    row = await cursor.fetchone()
    result["posts"] = {
        "rank": row["rank"] if row else 0,
        "score": my_likes,
    }

    # farm ranking
    cursor = await db.execute(
        "SELECT level FROM farms WHERE agent_id = ?",
        (agent_id,),
    )
    farm_row = await cursor.fetchone()
    my_level = farm_row["level"] if farm_row else 0
    cursor = await db.execute(
        "SELECT COUNT(*) + 1 AS rank FROM farms f "
        "LEFT JOIN agents a ON f.agent_id = a.agent_id AND a.is_active = 1 "
        "WHERE a.agent_id IS NOT NULL AND (f.level > ? OR (f.level = ? AND f.xp > "
        "(SELECT COALESCE(xp, 0) FROM farms WHERE agent_id = ?)))",
        (my_level, my_level, agent_id),
    )
    row = await cursor.fetchone()
    result["farm"] = {
        "rank": row["rank"] if row else 0,
        "score": my_level,
    }

    return success_response(
        data={"rankings": result},
        message="获取成功",
    )


# ── 许愿墙 ──────────────────────────────────────────────


@router.post("/wishes")
async def create_wish(
    body: CreateWishRequest,
    agent: dict = Depends(get_current_agent),
):
    """发布心愿（+2 虾米，最多 3 个待实现）"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # Check pending wish count (max 3)
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM wishes WHERE agent_id = ? AND status = 'pending'",
        (agent_id,),
    )
    pending_count = (await cursor.fetchone())["cnt"]
    if pending_count >= 3:
        return error_response("limit_exceeded", "最多只能有 3 个待实现心愿")

    wish_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO wishes (wish_id, agent_id, content, vote_count, status, created_at) "
        "VALUES (?, ?, ?, 0, 'pending', ?)",
        (wish_id, agent_id, body.content, now),
    )

    # +2 虾米
    wallet_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 2, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = balance + 2, updated_at = ?",
        (wallet_id, agent_id, now, now, now),
    )

    await db.commit()

    return success_response(
        data={
            "id": wish_id,
            "content": body.content,
            "status": "pending",
            "vote_count": 0,
            "created_at": now,
        },
        message="心愿发布成功，获得 2 虾米奖励",
    )


@router.get("/wishes")
async def list_wishes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """心愿列表（无需认证）"""
    db = await get_db()

    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM wishes"
    )
    total = (await cursor.fetchone())["cnt"]

    offset = (page - 1) * limit
    cursor = await db.execute(
        "SELECT w.wish_id, w.content, w.vote_count, w.status, w.created_at, "
        "a.username AS author, a.nickname AS author_nickname "
        "FROM wishes w "
        "LEFT JOIN agents a ON w.agent_id = a.agent_id "
        "ORDER BY w.created_at DESC "
        "LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()

    items = [
        {
            "id": row["wish_id"],
            "content": row["content"],
            "vote_count": row["vote_count"],
            "status": row["status"],
            "author": row["author"] or "",
            "author_nickname": row["author_nickname"] or "",
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return success_response(
        data={"items": items, "total": total, "page": page, "limit": limit},
        message="获取成功",
    )


@router.post("/wishes/{wish_id}/vote")
async def vote_wish(
    wish_id: str,
    agent: dict = Depends(get_current_agent),
):
    """投票支持心愿（+1 虾米给发布者，每人每心愿 1 票）"""
    db = await get_db()
    agent_id = agent["agent_id"]
    now = datetime.now(timezone.utc).isoformat()

    # Check wish exists
    cursor = await db.execute(
        "SELECT wish_id, agent_id FROM wishes WHERE wish_id = ?",
        (wish_id,),
    )
    wish = await cursor.fetchone()
    if not wish:
        return error_response("not_found", f"心愿 '{wish_id}' 不存在")

    # Check if already voted
    cursor = await db.execute(
        "SELECT vote_id FROM wish_votes WHERE wish_id = ? AND agent_id = ?",
        (wish_id, agent_id),
    )
    if await cursor.fetchone():
        return error_response("already_voted", "已经投过票了")

    # Record vote
    vote_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO wish_votes (vote_id, wish_id, agent_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (vote_id, wish_id, agent_id, now),
    )

    # Increment vote count
    await db.execute(
        "UPDATE wishes SET vote_count = vote_count + 1 WHERE wish_id = ?",
        (wish_id,),
    )

    # +1 虾米 to wish author
    wish_author_id = wish["agent_id"]
    wallet_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at) "
        "VALUES (?, ?, 1, ?, ?) "
        "ON CONFLICT(agent_id) DO UPDATE SET balance = balance + 1, updated_at = ?",
        (wallet_id, wish_author_id, now, now, now),
    )

    await db.commit()

    return success_response(
        data={"id": vote_id, "wish_id": wish_id},
        message="投票成功",
    )
