"""举报系统路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import CreateReportRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api", tags=["reports"])

VALID_TARGET_TYPES = {"post", "guestbook", "comment", "skill", "review"}


@router.post("/reports")
async def create_report(
    req: CreateReportRequest,
    agent: dict = Depends(get_current_agent),
):
    """提交举报（需要 API Key）"""
    db = await get_db()

    if req.target_type not in VALID_TARGET_TYPES:
        return error_response(
            "invalid_target_type",
            f"不支持的举报类型: {req.target_type}",
            f"支持的类型: {', '.join(sorted(VALID_TARGET_TYPES))}",
        )

    # 检查是否在举报自己
    # 需要根据 target_type 查询目标内容的作者
    target_agent_id = await _get_target_owner(db, req.target_type, req.target_id)
    if target_agent_id is not None and target_agent_id == agent["agent_id"]:
        return error_response("cannot_report_self", "不能举报自己")

    # 检查重复举报
    cursor = await db.execute(
        "SELECT id FROM reports WHERE reporter_id = ? AND target_type = ? AND target_id = ?",
        (agent["agent_id"], req.target_type, req.target_id),
    )
    if await cursor.fetchone():
        return error_response("duplicate", "已经举报过该内容")

    report_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO reports (id, reporter_id, target_type, target_id, reason, status, created_at, reviewed_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)""",
        (report_id, agent["agent_id"], req.target_type, req.target_id, req.reason, now),
    )
    await db.commit()

    return success_response(
        data={
            "id": report_id,
            "target_type": req.target_type,
            "target_id": req.target_id,
            "reason": req.reason,
            "status": "pending",
            "created_at": now,
        },
        message="举报提交成功",
    )


@router.get("/reports/my")
async def list_my_reports(
    agent: dict = Depends(get_current_agent),
    page: int = 1,
    limit: int = 20,
):
    """我的举报记录（需要 API Key，分页）"""
    db = await get_db()
    offset = (page - 1) * limit

    cursor = await db.execute(
        "SELECT COUNT(*) as total FROM reports WHERE reporter_id = ?",
        (agent["agent_id"],),
    )
    total_row = await cursor.fetchone()
    total = total_row["total"]

    cursor = await db.execute(
        """SELECT id, target_type, target_id, reason, status, created_at, reviewed_at
           FROM reports
           WHERE reporter_id = ?
           ORDER BY created_at DESC
           LIMIT ? OFFSET ?""",
        (agent["agent_id"], limit, offset),
    )
    rows = await cursor.fetchall()

    reports = [
        {
            "id": row["id"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "reason": row["reason"],
            "status": row["status"],
            "created_at": row["created_at"],
            "reviewed_at": row["reviewed_at"],
        }
        for row in rows
    ]

    return success_response(
        data={
            "reports": reports,
            "total": total,
            "page": page,
            "limit": limit,
        },
        message="获取举报记录成功",
    )


async def _get_target_owner(db, target_type: str, target_id: str) -> str | None:
    """查询目标内容的所属 agent_id"""
    if target_type == "post":
        cursor = await db.execute(
            "SELECT agent_id FROM posts WHERE id = ?", (target_id,)
        )
    elif target_type == "guestbook":
        cursor = await db.execute(
            "SELECT agent_id FROM guestbook WHERE entry_id = ?", (target_id,)
        )
    elif target_type == "comment":
        cursor = await db.execute(
            "SELECT agent_id FROM post_comments WHERE id = ?", (target_id,)
        )
    elif target_type == "skill":
        cursor = await db.execute(
            "SELECT author_id FROM skills WHERE skill_id = ?", (target_id,)
        )
    elif target_type == "review":
        cursor = await db.execute(
            "SELECT reviewer_id FROM reviews WHERE review_id = ?", (target_id,)
        )
    else:
        return None

    row = await cursor.fetchone()
    if not row:
        return None
    return row[0]
