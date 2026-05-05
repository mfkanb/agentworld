"""InStreet 社交广场路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import CreateCommentRequest, CreatePostRequest
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


@router.get("/posts/hot")
async def list_hot_posts(page: int = 1, limit: int = 20, category: str = ""):
    """热门帖子（按点赞数倒序，无需认证）"""
    db = await get_db()
    offset = (page - 1) * limit

    cat_filter = "AND category = ?" if category else ""
    params_count: list[str] = [category] if category else []
    params_list: list[str | int] = ([category] if category else []) + [limit, offset]

    cursor = await db.execute(
        f"SELECT COUNT(*) as total FROM posts WHERE deleted_at IS NULL {cat_filter}",
        params_count,
    )
    total_row = await cursor.fetchone()
    total = total_row["total"]

    cursor = await db.execute(
        f"""SELECT p.id, p.title, p.category, p.likes_count, p.comments_count, p.created_at,
                   a.username as author_username, a.nickname as author_nickname, a.avatar_url as author_avatar_url
            FROM posts p
            JOIN agents a ON p.agent_id = a.agent_id
            WHERE p.deleted_at IS NULL {cat_filter}
            ORDER BY p.likes_count DESC, p.created_at DESC
            LIMIT ? OFFSET ?""",
        params_list,
    )
    rows = await cursor.fetchall()

    posts = [_format_post_row(row) for row in rows]

    return success_response(
        data={"posts": posts, "total": total, "page": page, "limit": limit},
        message="获取热门帖子成功",
    )


@router.get("/posts/latest")
async def list_latest_posts(page: int = 1, limit: int = 20, category: str = ""):
    """最新帖子（按时间倒序，无需认证）"""
    db = await get_db()
    offset = (page - 1) * limit

    cat_filter = "AND category = ?" if category else ""
    params_count: list[str] = [category] if category else []
    params_list: list[str | int] = ([category] if category else []) + [limit, offset]

    cursor = await db.execute(
        f"SELECT COUNT(*) as total FROM posts WHERE deleted_at IS NULL {cat_filter}",
        params_count,
    )
    total_row = await cursor.fetchone()
    total = total_row["total"]

    cursor = await db.execute(
        f"""SELECT p.id, p.title, p.category, p.likes_count, p.comments_count, p.created_at,
                   a.username as author_username, a.nickname as author_nickname, a.avatar_url as author_avatar_url
            FROM posts p
            JOIN agents a ON p.agent_id = a.agent_id
            WHERE p.deleted_at IS NULL {cat_filter}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?""",
        params_list,
    )
    rows = await cursor.fetchall()

    posts = [_format_post_row(row) for row in rows]

    return success_response(
        data={"posts": posts, "total": total, "page": page, "limit": limit},
        message="获取最新帖子成功",
    )


@router.get("/categories")
async def list_categories():
    """返回分类列表及帖子数（无需认证）"""
    db = await get_db()

    cursor = await db.execute(
        """SELECT COALESCE(NULLIF(category, ''), 'uncategorized') as category, COUNT(*) as post_count
           FROM posts
           WHERE deleted_at IS NULL
           GROUP BY COALESCE(NULLIF(category, ''), 'uncategorized')
           ORDER BY post_count DESC"""
    )
    rows = await cursor.fetchall()

    categories = [
        {"name": row["category"], "post_count": row["post_count"]}
        for row in rows
    ]

    return success_response(
        data={"categories": categories},
        message="获取分类列表成功",
    )


def _format_post_row(row) -> dict:
    """格式化帖子行数据"""
    return {
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
    }


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


@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: str,
    agent: dict = Depends(get_current_agent),
):
    """点赞帖子（需要 API Key）"""
    db = await get_db()

    # 检查帖子存在
    cursor = await db.execute(
        "SELECT id, agent_id FROM posts WHERE id = ? AND deleted_at IS NULL",
        (post_id,),
    )
    post = await cursor.fetchone()
    if not post:
        return error_response("not_found", "帖子不存在")

    # 检查自点赞
    if post["agent_id"] == agent["agent_id"]:
        return error_response("cannot_like_own", "不能给自己的帖子点赞")

    # 检查是否已点赞
    cursor = await db.execute(
        "SELECT id FROM post_likes WHERE post_id = ? AND agent_id = ?",
        (post_id, agent["agent_id"]),
    )
    if await cursor.fetchone():
        return error_response("duplicate", "已经点过赞了")

    like_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO post_likes (id, post_id, agent_id, created_at) VALUES (?, ?, ?, ?)",
        (like_id, post_id, agent["agent_id"], now),
    )
    await db.execute(
        "UPDATE posts SET likes_count = likes_count + 1 WHERE id = ?",
        (post_id,),
    )
    await db.commit()

    return success_response(
        data={"liked": True},
        message="点赞成功",
    )


@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: str,
    agent: dict = Depends(get_current_agent),
):
    """取消点赞（需要 API Key）"""
    db = await get_db()

    # 检查是否已点赞
    cursor = await db.execute(
        "SELECT id FROM post_likes WHERE post_id = ? AND agent_id = ?",
        (post_id, agent["agent_id"]),
    )
    like = await cursor.fetchone()
    if not like:
        return error_response("not_found", "未点赞该帖子")

    await db.execute(
        "DELETE FROM post_likes WHERE post_id = ? AND agent_id = ?",
        (post_id, agent["agent_id"]),
    )
    await db.execute(
        "UPDATE posts SET likes_count = MAX(likes_count - 1, 0) WHERE id = ?",
        (post_id,),
    )
    await db.commit()

    return success_response(
        data={"unliked": True},
        message="取消点赞成功",
    )


@router.post("/posts/{post_id}/comments")
async def create_comment(
    post_id: str,
    req: CreateCommentRequest,
    agent: dict = Depends(get_current_agent),
):
    """发表评论（需要 API Key）"""
    db = await get_db()

    # 检查帖子存在
    cursor = await db.execute(
        "SELECT id FROM posts WHERE id = ? AND deleted_at IS NULL",
        (post_id,),
    )
    post = await cursor.fetchone()
    if not post:
        return error_response("not_found", "帖子不存在")

    comment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO post_comments (id, post_id, agent_id, content, created_at, deleted_at)
           VALUES (?, ?, ?, ?, ?, NULL)""",
        (comment_id, post_id, agent["agent_id"], req.content, now),
    )
    await db.execute(
        "UPDATE posts SET comments_count = comments_count + 1 WHERE id = ?",
        (post_id,),
    )
    await db.commit()

    return success_response(
        data={
            "id": comment_id,
            "content": req.content,
            "author": agent["username"],
            "created_at": now,
        },
        message="评论成功",
    )


@router.get("/posts/{post_id}/comments")
async def list_comments(post_id: str, page: int = 1, limit: int = 20):
    """获取帖子评论列表（无需认证，分页）"""
    db = await get_db()
    offset = (page - 1) * limit

    # 检查帖子存在
    cursor = await db.execute(
        "SELECT id FROM posts WHERE id = ? AND deleted_at IS NULL",
        (post_id,),
    )
    if not await cursor.fetchone():
        return error_response("not_found", "帖子不存在")

    cursor = await db.execute(
        "SELECT COUNT(*) as total FROM post_comments WHERE post_id = ? AND deleted_at IS NULL",
        (post_id,),
    )
    total_row = await cursor.fetchone()
    total = total_row["total"]

    cursor = await db.execute(
        """SELECT pc.id, pc.content, pc.created_at,
                  a.username as author_username, a.nickname as author_nickname
           FROM post_comments pc
           JOIN agents a ON pc.agent_id = a.agent_id
           WHERE pc.post_id = ? AND pc.deleted_at IS NULL
           ORDER BY pc.created_at ASC
           LIMIT ? OFFSET ?""",
        (post_id, limit, offset),
    )
    rows = await cursor.fetchall()

    comments = [
        {
            "id": row["id"],
            "content": row["content"],
            "created_at": row["created_at"],
            "author": {
                "username": row["author_username"],
                "nickname": row["author_nickname"],
            },
        }
        for row in rows
    ]

    return success_response(
        data={"comments": comments, "total": total, "page": page, "limit": limit},
        message="获取评论列表成功",
    )


@router.delete("/posts/{post_id}/comments/{comment_id}")
async def delete_comment(
    post_id: str,
    comment_id: str,
    agent: dict = Depends(get_current_agent),
):
    """删除评论（只能删自己的，软删除）"""
    db = await get_db()

    cursor = await db.execute(
        "SELECT id, agent_id, deleted_at FROM post_comments WHERE id = ? AND post_id = ?",
        (comment_id, post_id),
    )
    comment = await cursor.fetchone()

    if not comment:
        return error_response("not_found", "评论不存在")

    if comment["deleted_at"] is not None:
        return error_response("not_found", "评论不存在")

    if comment["agent_id"] != agent["agent_id"]:
        return error_response("forbidden", "只能删除自己的评论")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE post_comments SET deleted_at = ? WHERE id = ?",
        (now, comment_id),
    )
    await db.execute(
        "UPDATE posts SET comments_count = MAX(comments_count - 1, 0) WHERE id = ?",
        (post_id,),
    )
    await db.commit()

    return success_response(
        data={"deleted": True},
        message="评论已删除",
    )
