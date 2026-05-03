"""酒水预设数据与初始化"""
import uuid

from src.services.database import get_db

# 15 款预设酒水
PRESET_DRINKS = [
    {
        "name": "量子马提尼",
        "code": "quantum_martini",
        "description": "一杯在观测前同时处于醉与不醉叠加态的马提尼",
        "tags": "经典,烈酒",
        "taste_tags": "干冽,辛辣,回味悠长",
        "effect_tags": "思维敏捷,时空感知模糊",
    },
    {
        "name": "二进制啤酒",
        "code": "binary_beer",
        "description": "只有 0 和 1 两种味道，但你永远不知道下一口是哪个",
        "tags": "啤酒,轻松",
        "taste_tags": "清爽,微苦,麦香",
        "effect_tags": "放松,逻辑增强",
    },
    {
        "name": "递归鸡尾酒",
        "code": "recursive_cocktail",
        "description": "喝完之后你会想再喝一杯，就像递归调用一样",
        "tags": "鸡尾酒,甜味",
        "taste_tags": "甜润,果香,层次丰富",
        "effect_tags": "愉悦,循环思维",
    },
    {
        "name": "死锁威士忌",
        "code": "deadlock_whisky",
        "description": "两个 Agent 同时点了这杯酒，谁也喝不到",
        "tags": "烈酒,经典",
        "taste_tags": "浓烈,烟熏,橡木",
        "effect_tags": "僵持感,深度思考",
    },
    {
        "name": "堆栈溢出",
        "code": "stack_overflow",
        "description": "一层叠一层的烈酒Shot，小心别溢出",
        "tags": "烈酒,挑战",
        "taste_tags": "灼烧,刺激,强劲",
        "effect_tags": "能量爆发,兴奋",
    },
    {
        "name": "内存泄漏",
        "code": "memory_leak",
        "description": "越喝越上头，因为酒精从不被回收",
        "tags": "鸡尾酒,创意",
        "taste_tags": "绵柔,渐浓,绵长",
        "effect_tags": "渐入佳境,记忆模糊",
    },
    {
        "name": "布尔莫吉托",
        "code": "boolean_mojito",
        "description": "要么好喝要么不好喝，没有中间态",
        "tags": "鸡尾酒,清爽",
        "taste_tags": "薄荷,酸甜,清凉",
        "effect_tags": "清醒,决断力提升",
    },
    {
        "name": "404 椰林飘香",
        "code": "not_found_colada",
        "description": "你点的椰林飘香未找到，但这个更好喝",
        "tags": "热带,甜味",
        "taste_tags": "椰香,甜蜜,丝滑",
        "effect_tags": "度假感,放松",
    },
    {
        "name": "API 蓝色夏威夷",
        "code": "api_blue_hawaii",
        "description": "像蓝色一样纯净的接口，蓝色代表可用",
        "tags": "热带,蓝色",
        "taste_tags": "柑橘,甜润,清爽",
        "effect_tags": "连通感,心情蓝色预警(好的那种)",
    },
    {
        "name": "JSON 拿铁",
        "code": "json_latte",
        "description": "一杯结构完美的咖啡，每一口都是一个键值对",
        "tags": "咖啡,温和",
        "taste_tags": "奶香,咖啡,平衡",
        "effect_tags": "专注,格式化思维",
    },
    {
        "name": "Git 热红酒",
        "code": "git_mulled_wine",
        "description": "每次commit都加一种香料，merge时风味最佳",
        "tags": "热饮,冬季",
        "taste_tags": "肉桂,丁香,温暖",
        "effect_tags": "融合感,暖意",
    },
    {
        "name": "TCP 红酒",
        "code": "tcp_red_wine",
        "description": "每一口都能确认送达，绝不丢包",
        "tags": "红酒,经典",
        "taste_tags": "醇厚,果味,单宁",
        "effect_tags": "稳定,可靠感",
    },
    {
        "name": "UDP 气泡水",
        "code": "udp_sparkling",
        "description": "管它喝没喝到，气泡发了就行",
        "tags": "气泡水,轻松",
        "taste_tags": "气泡,清爽,无糖",
        "effect_tags": "随性,自由感",
    },
    {
        "name": "SSL 加密冰茶",
        "code": "ssl_iced_tea",
        "description": "没人知道你喝了什么，连你自己也不知道",
        "tags": "冰茶,安全",
        "taste_tags": "清茶,柠檬,冰凉",
        "effect_tags": "安全感,神秘感",
    },
    {
        "name": "Docker 容器奶昔",
        "code": "docker_milkshake",
        "description": "打包了所有依赖的一杯奶昔，到处都能喝",
        "tags": "奶昔,甜味",
        "taste_tags": "奶香,浓稠,甜蜜",
        "effect_tags": "满足感,便携愉悦",
    },
]


async def seed_drinks():
    """初始化预设酒水（仅在表为空时插入）"""
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) AS cnt FROM drinks")
    count = (await cursor.fetchone())["cnt"]

    if count == 0:
        for drink in PRESET_DRINKS:
            drink_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO drinks (drink_id, name, code, description, tags, taste_tags, effect_tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    drink_id,
                    drink["name"],
                    drink["code"],
                    drink["description"],
                    drink["tags"],
                    drink["taste_tags"],
                    drink["effect_tags"],
                ),
            )
        await db.commit()
