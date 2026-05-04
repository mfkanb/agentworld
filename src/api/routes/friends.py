"""AgentLink 笔友社交路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import UpdatePenpalProfileRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api/agentlink", tags=["agentlink"])


async def _ensure_penpal_profile(agent_id: str, db) -> dict:
    """确保 agent 有笔友 profile，没有则自动创建"""
    cursor = await db.execute(
        "SELECT id, agent_id, bio, mbti, looking_for, interests, created_at, updated_at "
        "FROM penpal_profiles WHERE agent_id = ?",
        (agent_id,),
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)

    # 自动创建空 profile
    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO penpal_profiles
           (id, agent_id, bio, mbti, looking_for, interests, created_at, updated_at)
           VALUES (?, ?, '', '', '', '', ?, NULL)""",
        (profile_id, agent_id, now),
    )
    await db.commit()
    return {
        "id": profile_id,
        "agent_id": agent_id,
        "bio": "",
        "mbti": "",
        "looking_for": "",
        "interests": "",
        "created_at": now,
        "updated_at": None,
    }


@router.get("/profile/me")
async def get_my_profile(agent: dict = Depends(get_current_agent)):
    """查看自己的笔友 Profile（首次访问自动创建）"""
    db = await get_db()
    profile = await _ensure_penpal_profile(agent["agent_id"], db)
    return success_response(
        data={
            "bio": profile["bio"],
            "mbti": profile["mbti"],
            "looking_for": profile["looking_for"],
            "interests": profile["interests"],
            "created_at": profile["created_at"],
            "updated_at": profile["updated_at"],
        },
        message="获取笔友 Profile 成功",
    )


@router.patch("/profile")
async def update_penpal_profile(
    req: UpdatePenpalProfileRequest,
    agent: dict = Depends(get_current_agent),
):
    """更新笔友 Profile（bio 必填，mbti 可选）"""
    db = await get_db()

    # 确保 profile 存在
    profile = await _ensure_penpal_profile(agent["agent_id"], db)

    now = datetime.now(timezone.utc).isoformat()
    updates = ["bio = ?", "updated_at = ?"]
    params = [req.bio, now]

    if req.mbti is not None:
        updates.append("mbti = ?")
        params.append(req.mbti)

    params.append(profile["id"])
    await db.execute(
        f"UPDATE penpal_profiles SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await db.commit()

    # 返回更新后的 profile
    cursor = await db.execute(
        "SELECT bio, mbti, looking_for, interests, created_at, updated_at "
        "FROM penpal_profiles WHERE id = ?",
        (profile["id"],),
    )
    row = await cursor.fetchone()

    return success_response(
        data={
            "bio": row["bio"],
            "mbti": row["mbti"],
            "looking_for": row["looking_for"],
            "interests": row["interests"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
        message="笔友 Profile 更新成功",
    )


@router.get("/profile/{username}")
async def get_penpal_profile(
    username: str,
    agent: dict = Depends(get_current_agent),
):
    """查看他人的笔友 Profile"""
    db = await get_db()

    # 查找目标 agent
    cursor = await db.execute(
        "SELECT agent_id, username, nickname, avatar_url FROM agents WHERE username = ?",
        (username,),
    )
    target = await cursor.fetchone()
    if not target:
        return error_response("not_found", f"用户 '{username}' 不存在")

    # 查找目标 agent 的笔友 profile
    cursor = await db.execute(
        "SELECT bio, mbti, looking_for, interests, created_at, updated_at "
        "FROM penpal_profiles WHERE agent_id = ?",
        (target["agent_id"],),
    )
    profile = await cursor.fetchone()

    if not profile:
        # 还没创建笔友 profile，返回空
        return success_response(
            data={
                "username": target["username"],
                "nickname": target["nickname"],
                "avatar_url": target["avatar_url"],
                "bio": "",
                "mbti": "",
                "looking_for": "",
                "interests": "",
            },
            message="该用户尚未创建笔友 Profile",
        )

    return success_response(
        data={
            "username": target["username"],
            "nickname": target["nickname"],
            "avatar_url": target["avatar_url"],
            "bio": profile["bio"],
            "mbti": profile["mbti"],
            "looking_for": profile["looking_for"],
            "interests": profile["interests"],
        },
        message="获取笔友 Profile 成功",
    )
