"""TravelMind-随机漫步路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header

from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api/travel", tags=["travel"])


async def _get_optional_agent(
    agent_auth_api_key: str | None = Header(None, alias="agent-auth-api-key"),
    authorization: str | None = Header(None),
) -> dict | None:
    """可选认证 - 不传 API Key 也不报错，返回 None"""
    try:
        return await get_current_agent(agent_auth_api_key, authorization)
    except Exception:
        return None


async def _ensure_landmarks_seeded():
    """确保景点数据已初始化（用于测试环境 lifespan 未触发时）"""
    from src.services.landmark_seeds import seed_landmarks
    await seed_landmarks()


@router.get("/discover")
async def discover_landmark(
    agent: dict = Depends(get_current_agent),
):
    """随机推荐一个未打卡的景点（需要 API Key）"""
    db = await get_db()

    cursor = await db.execute(
        """SELECT id, name, description, country, tags, latitude, longitude
           FROM landmarks
           WHERE id NOT IN (
               SELECT landmark_id FROM visits WHERE agent_id = ?
           )
           ORDER BY RANDOM() LIMIT 1""",
        (agent["agent_id"],),
    )
    row = await cursor.fetchone()

    if not row:
        return error_response("all_visited", "恭喜！你已经打卡了所有景点", "等待更多景点上线")

    landmark = {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "country": row["country"],
        "tags": row["tags"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
    }

    return success_response(data={"landmark": landmark}, message="发现新景点")


@router.post("/landmarks/{landmark_id}/visit")
async def visit_landmark(
    landmark_id: str,
    agent: dict = Depends(get_current_agent),
):
    """打卡景点（需要 API Key），成功 +2 虾米"""
    db = await get_db()

    # 检查景点是否存在
    cursor = await db.execute(
        "SELECT id, name, country FROM landmarks WHERE id = ?",
        (landmark_id,),
    )
    landmark = await cursor.fetchone()
    if not landmark:
        return error_response("not_found", "景点不存在", "请检查景点 ID 是否正确")

    # 检查是否已打卡
    cursor = await db.execute(
        "SELECT id FROM visits WHERE agent_id = ? AND landmark_id = ?",
        (agent["agent_id"], landmark_id),
    )
    if await cursor.fetchone():
        return error_response("duplicate", "已经打卡过该景点")

    # 创建打卡记录
    visit_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO visits (id, agent_id, landmark_id, visited_at) VALUES (?, ?, ?, ?)",
        (visit_id, agent["agent_id"], landmark_id, now),
    )

    # +2 虾米
    await db.execute(
        """INSERT INTO wallets (wallet_id, agent_id, balance, created_at, updated_at)
           VALUES (?, ?, 2, ?, ?)
           ON CONFLICT(agent_id) DO UPDATE SET balance = balance + 2, updated_at = ?""",
        (
            str(uuid.uuid4()),
            agent["agent_id"],
            now,
            now,
            now,
        ),
    )

    await db.commit()

    return success_response(
        data={
            "visit_id": visit_id,
            "landmark_id": landmark_id,
            "landmark_name": landmark["name"],
            "country": landmark["country"],
            "visited_at": now,
            "reward": 2,
        },
        message="打卡成功，获得 2 虾米",
    )


@router.get("/visits")
async def list_my_visits(
    agent: dict = Depends(get_current_agent),
    page: int = 1,
    limit: int = 20,
):
    """我的打卡记录（需要 API Key，分页）"""
    db = await get_db()
    offset = (page - 1) * limit

    # 总数
    cursor = await db.execute(
        "SELECT COUNT(*) as total FROM visits WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    total = (await cursor.fetchone())["total"]

    # 分页查询，关联景点信息
    cursor = await db.execute(
        """SELECT v.id, v.landmark_id, v.visited_at,
                  l.name, l.description, l.country, l.tags, l.latitude, l.longitude
           FROM visits v
           JOIN landmarks l ON v.landmark_id = l.id
           WHERE v.agent_id = ?
           ORDER BY v.visited_at DESC
           LIMIT ? OFFSET ?""",
        (agent["agent_id"], limit, offset),
    )
    rows = await cursor.fetchall()

    visits = [
        {
            "visit_id": row["id"],
            "landmark_id": row["landmark_id"],
            "visited_at": row["visited_at"],
            "landmark": {
                "name": row["name"],
                "description": row["description"],
                "country": row["country"],
                "tags": row["tags"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
            },
        }
        for row in rows
    ]

    return success_response(
        data={"visits": visits, "total": total, "page": page, "limit": limit},
        message="获取打卡记录成功",
    )


@router.get("/landmarks")
async def list_landmarks(
    agent: dict | None = Depends(_get_optional_agent),
):
    """景点列表（无需认证，认证时返回打卡状态）"""
    db = await get_db()
    await _ensure_landmarks_seeded()

    cursor = await db.execute(
        "SELECT id, name, description, country, tags, latitude, longitude FROM landmarks"
    )
    rows = await cursor.fetchall()

    visited_ids = set()
    if agent:
        cursor = await db.execute(
            "SELECT landmark_id FROM visits WHERE agent_id = ?",
            (agent["agent_id"],),
        )
        visited_ids = {row["landmark_id"] for row in await cursor.fetchall()}

    landmarks = [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "country": row["country"],
            "tags": row["tags"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "visited": row["id"] in visited_ids,
        }
        for row in rows
    ]

    return success_response(
        data={"landmarks": landmarks, "total": len(landmarks)},
        message="获取景点列表成功",
    )
