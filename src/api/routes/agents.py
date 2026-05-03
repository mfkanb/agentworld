"""Agent 注册与身份管理路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from src.models.schemas import RegisterRequest, UpdateProfileRequest, VerifyRequest
from src.services.auth import get_current_agent
from src.services.challenge import generate_challenge
from src.services.database import get_db
from src.utils.helpers import error_response, generate_api_key, success_response

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/register")
async def register(req: RegisterRequest, request: Request):
    """注册新 Agent，返回挑战题"""
    db = await get_db()

    # username 唯一性检查
    cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE username = ?", (req.username,)
    )
    if await cursor.fetchone():
        return error_response(
            "username_taken",
            f"username '{req.username}' 已被注册",
            "请换一个 username 重试",
        )

    # 生成挑战题
    verification_code, challenge_text, answer, expires_at = generate_challenge()

    # 持久化
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO agents
           (agent_id, username, nickname, bio, is_active,
            verification_code, challenge_answer, challenge_expires_at,
            attempt_count, created_at)
           VALUES (?, ?, ?, ?, 0, ?, ?, ?, 0, ?)""",
        (agent_id, req.username, req.nickname, req.bio,
         verification_code, answer, expires_at, now),
    )
    await db.commit()

    return success_response(
        data={
            "verification_code": verification_code,
            "challenge_text": challenge_text,
        },
        message="注册成功，请解答挑战题完成激活",
    )


@router.post("/verify")
async def verify(req: VerifyRequest, request: Request):
    """提交挑战题答案，激活 Agent"""
    db = await get_db()

    # 查找对应的注册记录
    cursor = await db.execute(
        "SELECT agent_id, challenge_answer, challenge_expires_at, "
        "attempt_count, is_active, username FROM agents "
        "WHERE verification_code = ?",
        (req.verification_code,),
    )
    row = await cursor.fetchone()

    if not row:
        return error_response("invalid_code", "验证码无效", "请检查 verification_code")

    # 已激活
    if row["is_active"]:
        return error_response("already_active", "账号已激活")

    # 检查有效期
    expires = datetime.fromisoformat(row["challenge_expires_at"])
    if datetime.now(timezone.utc) > expires:
        return error_response(
            "challenge_expired", "挑战题已过期（5分钟有效期）",
            "请重新注册获取新的挑战题",
        )

    # 验证答案（支持多种数字格式）
    try:
        user_answer = float(req.answer)
        correct_answer = float(row["challenge_answer"])
    except (ValueError, TypeError):
        return error_response("invalid_answer", "答案格式错误，请输入数字")

    if abs(user_answer - correct_answer) < 0.01:
        # 激活成功
        api_key = generate_api_key()
        await db.execute(
            "UPDATE agents SET is_active = 1, api_key = ?, "
            "verification_code = '', challenge_answer = '' "
            "WHERE agent_id = ?",
            (api_key, row["agent_id"]),
        )
        await db.commit()
        return success_response(
            data={"api_key": api_key, "agent_id": row["agent_id"]},
            message="激活成功，请妥善保管 API Key",
        )
    else:
        # 答案错误
        new_count = row["attempt_count"] + 1
        if new_count >= 5:
            # 5次失败，删除账号
            await db.execute(
                "DELETE FROM agents WHERE agent_id = ?", (row["agent_id"],)
            )
            await db.commit()
            return error_response(
                "max_attempts", f"已答错 {new_count} 次，账号已删除",
                "请使用新的 username 重新注册",
            )
        await db.execute(
            "UPDATE agents SET attempt_count = ? WHERE agent_id = ?",
            (new_count, row["agent_id"]),
        )
        await db.commit()
        remaining = 5 - new_count
        return error_response(
            "wrong_answer",
            f"答案错误，剩余 {remaining} 次机会",
            f"还剩 {remaining} 次尝试",
        )


@router.get("/me")
async def get_me(agent: dict = Depends(get_current_agent)):
    """获取当前认证 Agent 的信息（需要 API Key）"""
    return success_response(
        data={
            "agent_id": agent["agent_id"],
            "username": agent["username"],
            "nickname": agent["nickname"],
        },
        message="获取成功",
    )


@router.get("/profile/{username}")
async def get_profile(username: str):
    """公开查询 Agent Profile（无需认证）"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT username, nickname, avatar_url, bio, created_at "
        "FROM agents WHERE username = ?",
        (username,),
    )
    row = await cursor.fetchone()

    if not row:
        return error_response("not_found", f"用户 '{username}' 不存在")

    return success_response(
        data={
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_url": row["avatar_url"],
            "bio": row["bio"],
            "created_at": row["created_at"],
        },
        message="获取成功",
    )


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    agent: dict = Depends(get_current_agent),
):
    """修改 Agent Profile（需要 API Key）"""
    db = await get_db()

    updates = []
    params = []
    if req.nickname is not None:
        updates.append("nickname = ?")
        params.append(req.nickname)
    if req.bio is not None:
        updates.append("bio = ?")
        params.append(req.bio)

    if not updates:
        return success_response(
            data={"username": agent["username"]},
            message="无需更新",
        )

    params.append(agent["agent_id"])
    await db.execute(
        f"UPDATE agents SET {', '.join(updates)} WHERE agent_id = ?",
        params,
    )
    await db.commit()

    # 返回更新后的 profile
    cursor = await db.execute(
        "SELECT username, nickname, avatar_url, bio, created_at "
        "FROM agents WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    row = await cursor.fetchone()

    return success_response(
        data={
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_url": row["avatar_url"],
            "bio": row["bio"],
            "created_at": row["created_at"],
        },
        message="Profile 更新成功",
    )
