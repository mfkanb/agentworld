"""虾评 - 技能浏览路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.models.schemas import CreateSkillRequest, UpdateSkillRequest
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
