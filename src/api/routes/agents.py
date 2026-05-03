"""Agent 注册与身份管理路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from src.models.schemas import RegisterRequest, VerifyRequest
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
