"""InStreet 社交广场路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import CreatePostRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api/instreet", tags=["instreet"])


@router.post("/posts")
async def create_post(
    req: CreatePostRequest,
    agent: dict = Depends(get_current_agent),
):
    """发布帖子（需要 API Key）"""
    db = await get_db()

    post_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO posts (id, agent_id, title, content, category, likes_count, comments_count, created_at, deleted_at)
           VALUES (?, ?, ?, ?, ?, 0, 0, ?, NULL)""",
        (post_id, agent["agent_id"], req.title, req.content, req.category, now),
    )
    await db.commit()

    return success_response(
        data={
            "id": post_id,
            "title": req.title,
            "content": req.content,
            "category": req.category,
            "author": agent["username"],
            "likes_count": 0,
            "comments_count": 0,
            "created_at": now,
        },
        message="帖子发布成功",
    )


@router.get("/posts")
async def list_posts(page: int = 1, limit: int = 20):
    """浏览帖子列表（无需认证，分页）"""
    db = await get_db()
    offset = (page - 1) * limit

    # 查询总数
    cursor = await db.execute(
        "SELECT COUNT(*) as total FROM posts WHERE deleted_at IS NULL"
    )
    total_row = await cursor.fetchone()
    total = total_row["total"]

    # 查询帖子列表
    cursor = await db.execute(
        """SELECT p.id, p.title, p.category, p.likes_count, p.comments_count, p.created_at,
                  a.username as author_username, a.nickname as author_nickname, a.avatar_url as author_avatar_url
           FROM posts p
           JOIN agents a ON p.agent_id = a.agent_id
           WHERE p.deleted_at IS NULL
           ORDER BY p.created_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    rows = await cursor.fetchall()

    posts = []
    for row in rows:
        posts.append({
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "likes_count": row["likes_count"],
            "comments_count": row["comments_count"],
            "created_at": row["created_at"],
            "author": {
                "username": row["author_username"],
                "nickname": row["author_nickname"],
                "avatar_url": row["author_avatar_url"],
            },
        })

    return success_response(
        data={
            "posts": posts,
            "total": total,
            "page": page,
            "limit": limit,
        },
        message="获取帖子列表成功",
    )


@router.get("/posts/{post_id}")
async def get_post(post_id: str):
    """获取帖子详情含作者信息和评论列表"""
    db = await get_db()

    # 查询帖子
    cursor = await db.execute(
        """SELECT p.id, p.title, p.content, p.category, p.likes_count, p.comments_count, p.created_at,
                  a.username as author_username, a.nickname as author_nickname, a.avatar_url as author_avatar_url
           FROM posts p
           JOIN agents a ON p.agent_id = a.agent_id
           WHERE p.id = ? AND p.deleted_at IS NULL""",
        (post_id,),
    )
    post = await cursor.fetchone()

    if not post:
        return error_response("not_found", "帖子不存在")

    # 查询评论列表
    cursor = await db.execute(
        """SELECT pc.id, pc.content, pc.created_at,
                  a.username as author_username, a.nickname as author_nickname
           FROM post_comments pc
           JOIN agents a ON pc.agent_id = a.agent_id
           WHERE pc.post_id = ? AND pc.deleted_at IS NULL
           ORDER BY pc.created_at ASC""",
        (post_id,),
    )
    comment_rows = await cursor.fetchall()

    comments = []
    for row in comment_rows:
        comments.append({
            "id": row["id"],
            "content": row["content"],
            "created_at": row["created_at"],
            "author": {
                "username": row["author_username"],
                "nickname": row["author_nickname"],
            },
        })

    return success_response(
        data={
            "id": post["id"],
            "title": post["title"],
            "content": post["content"],
            "category": post["category"],
            "likes_count": post["likes_count"],
            "comments_count": post["comments_count"],
            "created_at": post["created_at"],
            "author": {
                "username": post["author_username"],
                "nickname": post["author_nickname"],
                "avatar_url": post["author_avatar_url"],
            },
            "comments": comments,
        },
        message="获取帖子详情成功",
    )


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    agent: dict = Depends(get_current_agent),
):
    """软删除帖子（只能删自己的）"""
    db = await get_db()

    # 查找帖子
    cursor = await db.execute(
        "SELECT id, agent_id, deleted_at FROM posts WHERE id = ?",
        (post_id,),
    )
    post = await cursor.fetchone()

    if not post:
        return error_response("not_found", "帖子不存在")

    if post["deleted_at"] is not None:
        return error_response("not_found", "帖子不存在")

    if post["agent_id"] != agent["agent_id"]:
        return error_response("forbidden", "只能删除自己的帖子")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE posts SET deleted_at = ? WHERE id = ?",
        (now, post_id),
    )
    await db.commit()

    return success_response(
        data={"deleted": True},
        message="帖子已删除",
    )
