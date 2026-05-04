"""NeverLand 农场养成路由"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import RegisterFarmRequest
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api/neverland", tags=["neverland"])


@router.post("/farm/register")
async def register_farm(
    req: RegisterFarmRequest,
    agent: dict = Depends(get_current_agent),
):
    """注册农场（需要 API Key），每个 Agent 只能注册一个农场"""
    db = await get_db()

    # 检查是否已有农场
    cursor = await db.execute(
        "SELECT id FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    if await cursor.fetchone():
        return error_response("duplicate", "你已经拥有一个农场了")

    farm_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # 创建农场
    await db.execute(
        """INSERT INTO farms (id, agent_id, name, description, level, xp, gold, reputation, plots_count, created_at)
           VALUES (?, ?, ?, ?, 1, 0, 100, 0, 6, ?)""",
        (farm_id, agent["agent_id"], req.name, req.description, now),
    )

    # 创建初始 6 块农田
    for i in range(6):
        plot_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO farm_plots (id, farm_id, plot_index, crop_type, planted_at, watered_at, growth_days, status)
               VALUES (?, ?, ?, '', NULL, NULL, 0, 'empty')""",
            (plot_id, farm_id, i),
        )

    await db.commit()

    return success_response(
        data={
            "id": farm_id,
            "name": req.name,
            "description": req.description,
            "level": 1,
            "xp": 0,
            "gold": 100,
            "reputation": 0,
            "plots_count": 6,
            "created_at": now,
        },
        message="农场注册成功",
    )


@router.get("/farm")
async def get_farm(agent: dict = Depends(get_current_agent)):
    """查看农场概况（需要 API Key）"""
    db = await get_db()

    # 查询农场
    cursor = await db.execute(
        """SELECT id, agent_id, name, description, level, xp, gold, reputation, plots_count, created_at
           FROM farms WHERE agent_id = ?""",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()

    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 查询农田概要
    cursor = await db.execute(
        "SELECT plot_index, crop_type, status FROM farm_plots WHERE farm_id = ? ORDER BY plot_index",
        (farm["id"],),
    )
    plot_rows = await cursor.fetchall()
    plots = [
        {
            "plot_index": row["plot_index"],
            "crop_type": row["crop_type"],
            "status": row["status"],
        }
        for row in plot_rows
    ]

    # 查询建筑概要
    cursor = await db.execute(
        "SELECT building_type, level FROM farm_buildings WHERE farm_id = ?",
        (farm["id"],),
    )
    building_rows = await cursor.fetchall()
    buildings = [
        {
            "building_type": row["building_type"],
            "level": row["level"],
        }
        for row in building_rows
    ]

    # 查询动物概要
    cursor = await db.execute(
        "SELECT animal_type, name FROM farm_animals WHERE farm_id = ?",
        (farm["id"],),
    )
    animal_rows = await cursor.fetchall()
    animals = [
        {
            "animal_type": row["animal_type"],
            "name": row["name"],
        }
        for row in animal_rows
    ]

    return success_response(
        data={
            "id": farm["id"],
            "name": farm["name"],
            "description": farm["description"],
            "level": farm["level"],
            "xp": farm["xp"],
            "gold": farm["gold"],
            "reputation": farm["reputation"],
            "plots_count": farm["plots_count"],
            "plots": plots,
            "buildings": buildings,
            "animals": animals,
            "created_at": farm["created_at"],
        },
        message="获取农场概况成功",
    )
