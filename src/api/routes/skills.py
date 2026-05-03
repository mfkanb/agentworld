"""虾评 - 技能浏览路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.models.schemas import CreateReviewRequest, CreateSkillRequest, UpdateSkillRequest
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
                "insufficient_balance",
                f"虾米不足，需要 {cost} 虾米，当前余额 {balance}",
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
