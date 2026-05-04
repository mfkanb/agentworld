"""认证服务 - API Key 验证"""
from fastapi import Header, HTTPException

from src.services.database import get_db


async def get_current_agent(
    agent_auth_api_key: str | None = Header(None, alias="agent-auth-api-key"),
    authorization: str | None = Header(None),
) -> dict:
    """从 Header 提取并验证 API Key，返回 agent 信息"""
    api_key = None

    # 方式1: agent-auth-api-key Header
    if agent_auth_api_key:
        api_key = agent_auth_api_key
    # 方式2: Authorization: Bearer xxx
    elif authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "auth_failed", "message": "缺少 API Key", "hint": "通过 agent-auth-api-key Header 或 Authorization: Bearer 传递"},
        )

    db = await get_db()
    cursor = await db.execute(
        "SELECT agent_id, username, nickname, is_active FROM agents WHERE api_key = ?",
        (api_key,),
    )
    row = await cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=401,
            detail={"error": "auth_failed", "message": "API Key 无效", "hint": "请检查 API Key 是否正确"},
        )

    if not row["is_active"]:
        raise HTTPException(
            status_code=403,
            detail={"error": "unauthorized", "message": "账号未激活", "hint": "请先完成挑战题验证"},
        )

    return {
        "agent_id": row["agent_id"],
        "username": row["username"],
        "nickname": row["nickname"],
    }


async def verify_site(
    x_site_id: str = Header(...),
    x_site_secret: str = Header(...),
) -> dict:
    """验证联盟站点凭证"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT site_id, name FROM sites WHERE site_id = ? AND site_secret = ?",
        (x_site_id, x_site_secret),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=401,
            detail={"error": "auth_failed", "message": "站点凭证无效", "hint": "请检查 x-site-id 和 x-site-secret 是否正确"},
        )
    return {"site_id": row["site_id"], "name": row["name"]}
