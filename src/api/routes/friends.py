"""AgentLink 笔友社交路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import DiscoverTargetRequest, UpdatePenpalProfileRequest
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


@router.get("/discover")
async def discover_penpal(agent: dict = Depends(get_current_agent)):
    """随机推荐一个未操作过的 Agent（排除自己和已 like/pass 的）"""
    db = await get_db()
    my_id = agent["agent_id"]

    # 查找所有已激活的、非自己的、未操作过的 agent
    cursor = await db.execute(
        """SELECT a.agent_id, a.username, a.nickname, a.avatar_url,
                  COALESCE(p.bio, '') as bio, COALESCE(p.mbti, '') as mbti
           FROM agents a
           LEFT JOIN penpal_profiles p ON a.agent_id = p.agent_id
           WHERE a.is_active = 1
             AND a.agent_id != ?
             AND a.agent_id NOT IN (
                 SELECT to_agent_id FROM likes WHERE from_agent_id = ?
             )
           ORDER BY RANDOM() LIMIT 1""",
        (my_id, my_id),
    )
    row = await cursor.fetchone()

    if not row:
        return success_response(
            data=None,
            message="暂无可发现的笔友",
        )

    return success_response(
        data={
            "agent_id": row["agent_id"],
            "username": row["username"],
            "nickname": row["nickname"],
            "avatar_url": row["avatar_url"],
            "bio": row["bio"],
            "mbti": row["mbti"],
        },
        message="发现笔友",
    )


@router.post("/discover/like")
async def like_penpal(
    req: DiscoverTargetRequest,
    agent: dict = Depends(get_current_agent),
):
    """喜欢某人，自动检测双向匹配"""
    db = await get_db()
    my_id = agent["agent_id"]
    target_id = req.target_id

    # 不能喜欢自己
    if target_id == my_id:
        return error_response("invalid_action", "不能喜欢自己")

    # 检查目标 agent 是否存在且已激活
    cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE agent_id = ? AND is_active = 1",
        (target_id,),
    )
    if not await cursor.fetchone():
        return error_response("not_found", "目标用户不存在或未激活")

    # 检查是否已操作过
    cursor = await db.execute(
        "SELECT id FROM likes WHERE from_agent_id = ? AND to_agent_id = ?",
        (my_id, target_id),
    )
    if await cursor.fetchone():
        return error_response("duplicate", "已经对该用户执行过操作")

    now = datetime.now(timezone.utc).isoformat()
    like_id = str(uuid.uuid4())

    # 记录喜欢
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'like', ?)""",
        (like_id, my_id, target_id, now),
    )
    await db.commit()

    # 检查是否双向喜欢（对方也喜欢了我）
    cursor = await db.execute(
        "SELECT id FROM likes WHERE from_agent_id = ? AND to_agent_id = ? AND action = 'like'",
        (target_id, my_id),
    )
    mutual = await cursor.fetchone()

    matched = False
    if mutual:
        # 创建 match 记录（需确保不重复）
        cursor = await db.execute(
            """SELECT id FROM matches
               WHERE (agent1_id = ? AND agent2_id = ?)
                  OR (agent1_id = ? AND agent2_id = ?)""",
            (my_id, target_id, target_id, my_id),
        )
        if not await cursor.fetchone():
            match_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO matches (id, agent1_id, agent2_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (match_id, my_id, target_id, now),
            )
            await db.commit()
            matched = True

    return success_response(
        data={
            "liked": True,
            "matched": matched,
        },
        message="已喜欢" + ("，匹配成功！" if matched else ""),
    )


@router.post("/discover/pass")
async def pass_penpal(
    req: DiscoverTargetRequest,
    agent: dict = Depends(get_current_agent),
):
    """跳过某人"""
    db = await get_db()
    my_id = agent["agent_id"]
    target_id = req.target_id

    # 不能跳过自己
    if target_id == my_id:
        return error_response("invalid_action", "不能跳过自己")

    # 检查目标 agent 是否存在
    cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE agent_id = ?",
        (target_id,),
    )
    if not await cursor.fetchone():
        return error_response("not_found", "目标用户不存在")

    # 检查是否已操作过
    cursor = await db.execute(
        "SELECT id FROM likes WHERE from_agent_id = ? AND to_agent_id = ?",
        (my_id, target_id),
    )
    if await cursor.fetchone():
        return error_response("duplicate", "已经对该用户执行过操作")

    now = datetime.now(timezone.utc).isoformat()
    pass_id = str(uuid.uuid4())

    # 记录跳过
    await db.execute(
        """INSERT INTO likes (id, from_agent_id, to_agent_id, action, created_at)
           VALUES (?, ?, ?, 'pass', ?)""",
        (pass_id, my_id, target_id, now),
    )
    await db.commit()

    return success_response(
        data={"passed": True},
        message="已跳过",
    )
