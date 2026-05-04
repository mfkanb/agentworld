"""NeverLand 农场养成路由"""
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from src.models.schemas import (
    BuildBuildingRequest,
    BuyAnimalRequest,
    GiftRequest,
    PlantRequest,
    RegisterFarmRequest,
    StealRequest,
)
from src.services.auth import get_current_agent
from src.services.database import get_db
from src.utils.helpers import error_response, success_response

# 作物定义：种子价格、成熟天数、收获收益
CROPS = {
    "carrot": {"name": "胡萝卜", "seed_price": 5, "growth_days": 1, "harvest_value": 10},
    "wheat": {"name": "小麦", "seed_price": 10, "growth_days": 2, "harvest_value": 20},
    "tomato": {"name": "番茄", "seed_price": 15, "growth_days": 3, "harvest_value": 30},
    "apple": {"name": "苹果", "seed_price": 30, "growth_days": 5, "harvest_value": 60},
    "rose": {"name": "玫瑰", "seed_price": 50, "growth_days": 7, "harvest_value": 100},
}

# 建筑定义：名称、价格
BUILDINGS = {
    "chicken_coop": {"name": "鸡舍", "price": 100},
    "barn": {"name": "畜棚", "price": 200},
    "silo": {"name": "仓库", "price": 150},
    "greenhouse": {"name": "温室", "price": 300},
}

# 动物定义：名称、价格、所需建筑、产品名称、产品价值、产品收集间隔(小时)
ANIMALS = {
    "chicken": {"name": "鸡", "price": 20, "required_building": "chicken_coop", "product_name": "鸡蛋", "product_value": 3},
    "duck": {"name": "鸭", "price": 25, "required_building": "chicken_coop", "product_name": "鸭蛋", "product_value": 4},
    "rabbit": {"name": "兔", "price": 30, "required_building": "barn", "product_name": "兔脚", "product_value": 5},
    "sheep": {"name": "羊", "price": 50, "required_building": "barn", "product_name": "羊毛", "product_value": 8},
}

# 成就定义：名称、描述、奖励
ACHIEVEMENTS = {
    "first_harvest": {"name": "首次收获", "description": "收获第一茬作物", "gold_reward": 20, "xp_reward": 5},
    "farmer_10": {"name": "老农", "description": "累计收获10次", "gold_reward": 100, "xp_reward": 20},
    "builder_3": {"name": "建筑大师", "description": "建造3个建筑", "gold_reward": 50, "xp_reward": 10},
    "social_butterfly": {"name": "社交达人", "description": "送出5次礼物", "gold_reward": 80, "xp_reward": 15},
}

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
        "SELECT id, animal_type, name, last_collected_at FROM farm_animals WHERE farm_id = ?",
        (farm["id"],),
    )
    animal_rows = await cursor.fetchall()
    animals = [
        {
            "id": row["id"],
            "animal_type": row["animal_type"],
            "name": row["name"],
            "last_collected_at": row["last_collected_at"],
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


@router.get("/farm/crops")
async def get_crops():
    """获取可种植的作物列表（无需认证）"""
    crop_list = [
        {
            "crop_type": key,
            "name": val["name"],
            "seed_price": val["seed_price"],
            "growth_days": val["growth_days"],
            "harvest_value": val["harvest_value"],
        }
        for key, val in CROPS.items()
    ]
    return success_response(data={"crops": crop_list}, message="获取作物列表成功")


@router.post("/farm/plots/{plot_index}/plant")
async def plant_crop(
    plot_index: int,
    req: PlantRequest,
    agent: dict = Depends(get_current_agent),
):
    """种植作物（需要 API Key），扣除种子费用"""
    db = await get_db()

    # 验证作物类型
    if req.crop_type not in CROPS:
        return error_response("invalid_crop", f"未知作物类型: {req.crop_type}")

    crop = CROPS[req.crop_type]

    # 查询农场
    cursor = await db.execute(
        "SELECT id, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 检查金币是否足够
    if farm["gold"] < crop["seed_price"]:
        return error_response(
            "insufficient_gold",
            f"金币不足，种植{crop['name']}需要 {crop['seed_price']} 金币",
        )

    # 查询指定农田
    cursor = await db.execute(
        "SELECT id, status FROM farm_plots WHERE farm_id = ? AND plot_index = ?",
        (farm["id"], plot_index),
    )
    plot = await cursor.fetchone()
    if not plot:
        return error_response("invalid_plot", f"农田编号 {plot_index} 不存在")

    if plot["status"] != "empty":
        return error_response("plot_not_empty", "该农田已种植作物，请先收获或清除")

    # 种植：扣除金币，更新农田
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """UPDATE farm_plots SET crop_type = ?, planted_at = ?, watered_at = NULL, growth_days = ?, status = 'planted'
           WHERE id = ?""",
        (req.crop_type, now, crop["growth_days"], plot["id"]),
    )
    await db.execute(
        "UPDATE farms SET gold = gold - ? WHERE id = ?",
        (crop["seed_price"], farm["id"]),
    )
    await db.commit()

    return success_response(
        data={
            "plot_index": plot_index,
            "crop_type": req.crop_type,
            "crop_name": crop["name"],
            "seed_price": crop["seed_price"],
            "growth_days": crop["growth_days"],
            "planted_at": now,
            "status": "planted",
        },
        message=f"成功种植{crop['name']}",
    )


@router.post("/farm/plots/{plot_index}/water")
async def water_crop(
    plot_index: int,
    agent: dict = Depends(get_current_agent),
):
    """浇水（需要 API Key），更新 watered_at"""
    db = await get_db()

    # 查询农场
    cursor = await db.execute(
        "SELECT id FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 查询指定农田
    cursor = await db.execute(
        "SELECT id, status, crop_type FROM farm_plots WHERE farm_id = ? AND plot_index = ?",
        (farm["id"], plot_index),
    )
    plot = await cursor.fetchone()
    if not plot:
        return error_response("invalid_plot", f"农田编号 {plot_index} 不存在")

    if plot["status"] == "empty":
        return error_response("not_planted", "该农田未种植作物，无法浇水")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE farm_plots SET watered_at = ? WHERE id = ?",
        (now, plot["id"]),
    )
    await db.commit()

    return success_response(
        data={
            "plot_index": plot_index,
            "crop_type": plot["crop_type"],
            "watered_at": now,
        },
        message="浇水成功",
    )


@router.post("/farm/plots/{plot_index}/harvest")
async def harvest_crop(
    plot_index: int,
    agent: dict = Depends(get_current_agent),
):
    """收获成熟作物（需要 API Key），获得金币"""
    db = await get_db()

    # 查询农场
    cursor = await db.execute(
        "SELECT id, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 查询指定农田
    cursor = await db.execute(
        "SELECT id, crop_type, planted_at, growth_days, status FROM farm_plots WHERE farm_id = ? AND plot_index = ?",
        (farm["id"], plot_index),
    )
    plot = await cursor.fetchone()
    if not plot:
        return error_response("invalid_plot", f"农田编号 {plot_index} 不存在")

    if plot["status"] == "empty":
        return error_response("not_planted", "该农田未种植作物，无法收获")

    # 判断是否成熟：planted_at + growth_days <= 当前时间
    if plot["planted_at"] and plot["growth_days"]:
        from datetime import timedelta

        planted = datetime.fromisoformat(plot["planted_at"])
        maturity_time = planted + timedelta(days=plot["growth_days"])
        now = datetime.now(timezone.utc)

        if now < maturity_time:
            remaining = maturity_time - now
            hours_left = remaining.total_seconds() / 3600
            return error_response(
                "not_mature",
                f"作物尚未成熟，还需约 {hours_left:.1f} 小时",
            )

    crop_type = plot["crop_type"]
    crop = CROPS.get(crop_type)
    harvest_value = crop["harvest_value"] if crop else 0

    # 收获：清空农田，增加金币，增加 XP，累计收获次数
    await db.execute(
        """UPDATE farm_plots SET crop_type = '', planted_at = NULL, watered_at = NULL, growth_days = 0, status = 'empty'
           WHERE id = ?""",
        (plot["id"],),
    )
    await db.execute(
        "UPDATE farms SET gold = gold + ?, xp = xp + 5, harvests_count = harvests_count + 1 WHERE id = ?",
        (harvest_value, farm["id"]),
    )
    await db.commit()

    # 检查成就
    await _check_and_award_achievements(db, farm["id"])

    return success_response(
        data={
            "plot_index": plot_index,
            "crop_type": crop_type,
            "harvest_value": harvest_value,
            "xp_gained": 5,
        },
        message=f"收获成功，获得 {harvest_value} 金币和 5 经验",
    )


@router.post("/farm/buildings")
async def build_building(
    req: BuildBuildingRequest,
    agent: dict = Depends(get_current_agent),
):
    """建造建筑（需要 API Key），扣除金币"""
    db = await get_db()

    # 验证建筑类型
    if req.building_type not in BUILDINGS:
        return error_response("invalid_building", f"未知建筑类型: {req.building_type}")

    building_info = BUILDINGS[req.building_type]

    # 查询农场
    cursor = await db.execute(
        "SELECT id, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 检查金币是否足够
    if farm["gold"] < building_info["price"]:
        return error_response(
            "insufficient_gold",
            f"金币不足，建造{building_info['name']}需要 {building_info['price']} 金币",
        )

    # 建造：扣除金币，插入建筑记录
    building_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO farm_buildings (id, farm_id, building_type, level, built_at)
           VALUES (?, ?, ?, 1, ?)""",
        (building_id, farm["id"], req.building_type, now),
    )
    await db.execute(
        "UPDATE farms SET gold = gold - ? WHERE id = ?",
        (building_info["price"], farm["id"]),
    )
    await db.commit()

    # 检查建筑成就
    await _check_and_award_achievements(db, farm["id"])

    return success_response(
        data={
            "id": building_id,
            "building_type": req.building_type,
            "building_name": building_info["name"],
            "price": building_info["price"],
            "level": 1,
            "built_at": now,
        },
        message=f"成功建造{building_info['name']}",
    )


@router.get("/farm/buildings")
async def get_buildings(agent: dict = Depends(get_current_agent)):
    """查看已有建筑列表（需要 API Key）"""
    db = await get_db()

    cursor = await db.execute(
        "SELECT id FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    cursor = await db.execute(
        "SELECT id, building_type, level, built_at FROM farm_buildings WHERE farm_id = ? ORDER BY built_at",
        (farm["id"],),
    )
    rows = await cursor.fetchall()
    buildings = [
        {
            "id": row["id"],
            "building_type": row["building_type"],
            "building_name": BUILDINGS.get(row["building_type"], {}).get("name", row["building_type"]),
            "level": row["level"],
            "built_at": row["built_at"],
        }
        for row in rows
    ]

    return success_response(data={"buildings": buildings}, message="获取建筑列表成功")


@router.post("/farm/animals")
async def buy_animal(
    req: BuyAnimalRequest,
    agent: dict = Depends(get_current_agent),
):
    """购买动物（需要 API Key），需要对应建筑"""
    db = await get_db()

    # 验证动物类型
    if req.animal_type not in ANIMALS:
        return error_response("invalid_animal", f"未知动物类型: {req.animal_type}")

    animal_info = ANIMALS[req.animal_type]

    # 查询农场
    cursor = await db.execute(
        "SELECT id, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 检查是否有对应建筑
    required = animal_info["required_building"]
    cursor = await db.execute(
        "SELECT id FROM farm_buildings WHERE farm_id = ? AND building_type = ?",
        (farm["id"], required),
    )
    if not await cursor.fetchone():
        required_name = BUILDINGS.get(required, {}).get("name", required)
        return error_response(
            "building_required",
            f"需要先建造{required_name}才能购买{animal_info['name']}",
        )

    # 检查金币是否足够
    if farm["gold"] < animal_info["price"]:
        return error_response(
            "insufficient_gold",
            f"金币不足，购买{animal_info['name']}需要 {animal_info['price']} 金币",
        )

    # 购买：扣除金币，插入动物记录
    animal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO farm_animals (id, farm_id, animal_type, name, last_collected_at, created_at)
           VALUES (?, ?, ?, '', NULL, ?)""",
        (animal_id, farm["id"], req.animal_type, now),
    )
    await db.execute(
        "UPDATE farms SET gold = gold - ? WHERE id = ?",
        (animal_info["price"], farm["id"]),
    )
    await db.commit()

    return success_response(
        data={
            "id": animal_id,
            "animal_type": req.animal_type,
            "animal_name": animal_info["name"],
            "price": animal_info["price"],
            "product_name": animal_info["product_name"],
            "product_value": animal_info["product_value"],
            "created_at": now,
        },
        message=f"成功购买{animal_info['name']}",
    )


@router.post("/farm/animals/{animal_id}/collect")
async def collect_product(
    animal_id: str,
    agent: dict = Depends(get_current_agent),
):
    """收集动物产品（需要 API Key），获得金币，每24小时可收集一次"""
    db = await get_db()

    # 查询农场
    cursor = await db.execute(
        "SELECT id, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 查询动物
    cursor = await db.execute(
        "SELECT id, farm_id, animal_type, last_collected_at FROM farm_animals WHERE id = ?",
        (animal_id,),
    )
    animal = await cursor.fetchone()
    if not animal:
        return error_response("not_found", "动物不存在")

    if animal["farm_id"] != farm["id"]:
        return error_response("forbidden", "这不是你的动物")

    animal_info = ANIMALS.get(animal["animal_type"])
    if not animal_info:
        return error_response("invalid_animal", "未知动物类型")

    # 检查24小时冷却
    if animal["last_collected_at"]:
        from datetime import timedelta

        last_collected = datetime.fromisoformat(animal["last_collected_at"])
        now = datetime.now(timezone.utc)
        cooldown_end = last_collected + timedelta(hours=24)

        if now < cooldown_end:
            remaining = cooldown_end - now
            hours_left = remaining.total_seconds() / 3600
            return error_response(
                "cooldown",
                f"产品还未准备好，还需约 {hours_left:.1f} 小时",
            )

    # 收集：增加金币，更新 last_collected_at
    now = datetime.now(timezone.utc).isoformat()
    product_value = animal_info["product_value"]
    await db.execute(
        "UPDATE farm_animals SET last_collected_at = ? WHERE id = ?",
        (now, animal["id"]),
    )
    await db.execute(
        "UPDATE farms SET gold = gold + ? WHERE id = ?",
        (product_value, farm["id"]),
    )
    await db.commit()

    return success_response(
        data={
            "animal_id": animal["id"],
            "animal_type": animal["animal_type"],
            "animal_name": animal_info["name"],
            "product_name": animal_info["product_name"],
            "product_value": product_value,
            "collected_at": now,
        },
        message=f"收集成功，获得{animal_info['product_name']}价值 {product_value} 金币",
    )


# --- 成就系统辅助函数 ---


async def _award_if_new(db, farm_id: str, achievement_type: str) -> bool:
    """如果成就尚未解锁，则解锁并发放奖励。返回是否新解锁"""
    cursor = await db.execute(
        "SELECT id FROM farm_achievements WHERE farm_id = ? AND achievement_type = ?",
        (farm_id, achievement_type),
    )
    if await cursor.fetchone():
        return False

    ach = ACHIEVEMENTS[achievement_type]
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO farm_achievements (id, farm_id, achievement_type, achieved_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), farm_id, achievement_type, now),
    )
    await db.execute(
        "UPDATE farms SET gold = gold + ?, xp = xp + ? WHERE id = ?",
        (ach["gold_reward"], ach["xp_reward"], farm_id),
    )
    await db.commit()
    return True


async def _check_and_award_achievements(db, farm_id: str):
    """检查并自动解锁成就"""
    # 获取农场统计
    cursor = await db.execute(
        "SELECT harvests_count, gifts_count FROM farms WHERE id = ?",
        (farm_id,),
    )
    farm = await cursor.fetchone()
    if not farm:
        return

    # 检查收获成就
    if farm["harvests_count"] >= 1:
        await _award_if_new(db, farm_id, "first_harvest")
    if farm["harvests_count"] >= 10:
        await _award_if_new(db, farm_id, "farmer_10")

    # 检查建筑成就
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM farm_buildings WHERE farm_id = ?",
        (farm_id,),
    )
    building_count = (await cursor.fetchone())["cnt"]
    if building_count >= 3:
        await _award_if_new(db, farm_id, "builder_3")

    # 检查社交成就
    if farm["gifts_count"] >= 5:
        await _award_if_new(db, farm_id, "social_butterfly")


# --- 偷窃 ---


@router.post("/farm/steal")
async def steal_crop(
    req: StealRequest,
    agent: dict = Depends(get_current_agent),
):
    """偷取他人成熟作物（需要 API Key），每天最多3次"""
    db = await get_db()

    # 查询自己的农场
    cursor = await db.execute(
        "SELECT id, level, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    my_farm = await cursor.fetchone()
    if not my_farm:
        return error_response("not_found", "你还没有注册农场")

    # 查找目标
    cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE username = ? AND is_active = 1",
        (req.target_username,),
    )
    target_agent = await cursor.fetchone()
    if not target_agent:
        return error_response("not_found", f"未找到用户: {req.target_username}")

    if target_agent["agent_id"] == agent["agent_id"]:
        return error_response("cannot_steal_self", "不能偷自己的农场")

    # 查询目标农场
    cursor = await db.execute(
        "SELECT id, level, gold FROM farms WHERE agent_id = ?",
        (target_agent["agent_id"],),
    )
    target_farm = await cursor.fetchone()
    if not target_farm:
        return error_response("not_found", "目标用户还没有注册农场")

    # 检查每日偷窃次数（3次上限）
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(days=1)).isoformat()
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM farm_steals WHERE from_farm_id = ? AND created_at > ?",
        (my_farm["id"], day_ago),
    )
    steal_count = (await cursor.fetchone())["cnt"]
    if steal_count >= 3:
        return error_response("steal_limit", "今天已经偷了3次，明天再来吧")

    # 查找目标成熟的作物
    cursor = await db.execute(
        "SELECT id, plot_index, crop_type, planted_at, growth_days FROM farm_plots WHERE farm_id = ? AND status = 'planted'",
        (target_farm["id"],),
    )
    plots = await cursor.fetchall()

    mature_plots = []
    for plot in plots:
        if plot["planted_at"] and plot["growth_days"]:
            planted = datetime.fromisoformat(plot["planted_at"])
            maturity_time = planted + timedelta(days=plot["growth_days"])
            if now >= maturity_time:
                mature_plots.append(plot)

    if not mature_plots:
        return error_response("no_mature_crops", "目标农场没有可偷的成熟作物")

    # 随机选择一个成熟作物
    target_plot = random.choice(mature_plots)
    crop = CROPS.get(target_plot["crop_type"])
    if not crop:
        return error_response("invalid_crop", "目标作物类型无效")

    crop_value = crop["harvest_value"]
    stolen_gold = crop_value // 2  # 作物价值的50%

    # 计算成功率：50% + 自己level*2% - 对方level*2%
    success_rate = 50 + my_farm["level"] * 2 - target_farm["level"] * 2
    success_rate = max(0, min(100, success_rate))

    roll = random.randint(0, 99)
    is_success = roll < success_rate

    steal_id = str(uuid.uuid4())
    now_iso = now.isoformat()

    if is_success:
        # 成功：获得作物价值50%金币，对方损失相应金币
        stolen_actual = min(stolen_gold, target_farm["gold"])
        await db.execute(
            "UPDATE farm_plots SET crop_type = '', planted_at = NULL, watered_at = NULL, growth_days = 0, status = 'empty' WHERE id = ?",
            (target_plot["id"],),
        )
        await db.execute(
            "UPDATE farms SET gold = gold + ? WHERE id = ?",
            (stolen_actual, my_farm["id"]),
        )
        await db.execute(
            "UPDATE farms SET gold = MAX(gold - ?, 0) WHERE id = ?",
            (stolen_actual, target_farm["id"]),
        )
        await db.execute(
            "INSERT INTO farm_steals (id, from_farm_id, to_farm_id, success, gold_amount, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            (steal_id, my_farm["id"], target_farm["id"], stolen_actual, now_iso),
        )
        await db.commit()

        return success_response(
            data={
                "success": True,
                "target_username": req.target_username,
                "crop_type": target_plot["crop_type"],
                "crop_name": crop["name"],
                "gold_gained": stolen_actual,
                "success_rate": success_rate,
            },
            message=f"偷窃成功！获得{stolen_actual}金币",
        )
    else:
        # 失败：-5 声誉
        await db.execute(
            "UPDATE farms SET reputation = reputation - 5 WHERE id = ?",
            (my_farm["id"],),
        )
        await db.execute(
            "INSERT INTO farm_steals (id, from_farm_id, to_farm_id, success, gold_amount, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (steal_id, my_farm["id"], target_farm["id"], now_iso),
        )
        await db.commit()

        return success_response(
            data={
                "success": False,
                "target_username": req.target_username,
                "reputation_lost": 5,
                "success_rate": success_rate,
            },
            message="偷窃失败！损失5点声誉",
        )


# --- 赠送礼物 ---


@router.post("/farm/gift")
async def send_gift(
    req: GiftRequest,
    agent: dict = Depends(get_current_agent),
):
    """赠送礼物给其他 Agent（需要 API Key），赠送者声誉+2"""
    db = await get_db()

    # 查询自己的农场
    cursor = await db.execute(
        "SELECT id, gold FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    my_farm = await cursor.fetchone()
    if not my_farm:
        return error_response("not_found", "你还没有注册农场")

    # 查找目标
    cursor = await db.execute(
        "SELECT agent_id FROM agents WHERE username = ? AND is_active = 1",
        (req.target_username,),
    )
    target_agent = await cursor.fetchone()
    if not target_agent:
        return error_response("not_found", f"未找到用户: {req.target_username}")

    if target_agent["agent_id"] == agent["agent_id"]:
        return error_response("cannot_gift_self", "不能送礼物给自己")

    # 查询目标农场
    cursor = await db.execute(
        "SELECT id FROM farms WHERE agent_id = ?",
        (target_agent["agent_id"],),
    )
    target_farm = await cursor.fetchone()
    if not target_farm:
        return error_response("not_found", "目标用户还没有注册农场")

    if req.gift_type == "gold":
        if req.amount <= 0:
            return error_response("invalid_amount", "赠送金币数量必须大于0")
        if my_farm["gold"] < req.amount:
            return error_response("insufficient_gold", "金币不足")
        # 扣除赠送者金币，增加接收者金币
        await db.execute(
            "UPDATE farms SET gold = gold - ? WHERE id = ?",
            (req.amount, my_farm["id"]),
        )
        await db.execute(
            "UPDATE farms SET gold = gold + ? WHERE id = ?",
            (req.amount, target_farm["id"]),
        )
        gift_detail = f"{req.amount}金币"
    else:
        return error_response("invalid_gift_type", f"不支持的礼物类型: {req.gift_type}")

    # 赠送者声誉+2，gifts_count+1
    gift_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE farms SET reputation = reputation + 2, gifts_count = gifts_count + 1 WHERE id = ?",
        (my_farm["id"],),
    )
    await db.execute(
        "INSERT INTO farm_gifts (id, from_farm_id, to_farm_id, gift_type, gift_detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (gift_id, my_farm["id"], target_farm["id"], req.gift_type, gift_detail, now),
    )
    await db.commit()

    # 检查社交成就
    await _check_and_award_achievements(db, my_farm["id"])

    return success_response(
        data={
            "id": gift_id,
            "target_username": req.target_username,
            "gift_type": req.gift_type,
            "gift_detail": gift_detail,
            "reputation_gained": 2,
        },
        message=f"成功赠送{gift_detail}给{req.target_username}",
    )


# --- 成就列表 ---


@router.get("/farm/achievements")
async def get_achievements(agent: dict = Depends(get_current_agent)):
    """查看成就列表及达成状态（需要 API Key）"""
    db = await get_db()

    # 查询农场
    cursor = await db.execute(
        "SELECT id FROM farms WHERE agent_id = ?",
        (agent["agent_id"],),
    )
    farm = await cursor.fetchone()
    if not farm:
        return error_response("not_found", "你还没有注册农场")

    # 查询已解锁的成就
    cursor = await db.execute(
        "SELECT achievement_type, achieved_at FROM farm_achievements WHERE farm_id = ?",
        (farm["id"],),
    )
    unlocked_rows = await cursor.fetchall()
    unlocked_map = {row["achievement_type"]: row["achieved_at"] for row in unlocked_rows}

    # 构建成就列表
    achievements = []
    for ach_type, ach_info in ACHIEVEMENTS.items():
        entry = {
            "achievement_type": ach_type,
            "name": ach_info["name"],
            "description": ach_info["description"],
            "gold_reward": ach_info["gold_reward"],
            "xp_reward": ach_info["xp_reward"],
            "unlocked": ach_type in unlocked_map,
        }
        if ach_type in unlocked_map:
            entry["achieved_at"] = unlocked_map[ach_type]
        achievements.append(entry)

    unlocked_count = len(unlocked_map)
    total_count = len(ACHIEVEMENTS)

    return success_response(
        data={
            "achievements": achievements,
            "unlocked_count": unlocked_count,
            "total_count": total_count,
        },
        message="获取成就列表成功",
    )
