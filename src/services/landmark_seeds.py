"""世界景点预设数据与初始化"""
import uuid

from src.services.database import get_db

# 20 个世界景点
PRESET_LANDMARKS = [
    {
        "name": "埃菲尔铁塔",
        "description": "巴黎的标志性建筑，建于1889年，高324米，是全球最具辨识度的地标之一",
        "country": "法国",
        "tags": "地标,建筑,浪漫",
        "latitude": 48.8584,
        "longitude": 2.2945,
    },
    {
        "name": "自由女神像",
        "description": "矗立在纽约港的自由象征，由法国赠予美国，代表自由与民主",
        "country": "美国",
        "tags": "地标,雕塑,自由",
        "latitude": 40.6892,
        "longitude": -74.0445,
    },
    {
        "name": "万里长城",
        "description": "横跨中国北方的古代防御工程，绵延万里，是人类建筑史上的奇迹",
        "country": "中国",
        "tags": "古迹,建筑,世界遗产",
        "latitude": 40.4319,
        "longitude": 116.5704,
    },
    {
        "name": "富士山",
        "description": "日本最高峰，海拔3776米，完美锥形山体是日本精神文化的象征",
        "country": "日本",
        "tags": "自然,山脉,火山",
        "latitude": 35.3606,
        "longitude": 138.7274,
    },
    {
        "name": "大本钟",
        "description": "伦敦威斯敏斯特宫北端的著名钟楼，是英国最具标志性的建筑之一",
        "country": "英国",
        "tags": "地标,建筑,钟楼",
        "latitude": 51.5007,
        "longitude": -0.1246,
    },
    {
        "name": "悉尼歌剧院",
        "description": "位于悉尼港畔，独特的帆形屋顶设计使其成为20世纪最具创意的建筑之一",
        "country": "澳大利亚",
        "tags": "建筑,艺术,地标",
        "latitude": -33.8568,
        "longitude": 151.2153,
    },
    {
        "name": "吉萨金字塔",
        "description": "古埃及法老的陵墓，已有4500多年历史，是古代世界七大奇迹中唯一存世的",
        "country": "埃及",
        "tags": "古迹,建筑,神秘",
        "latitude": 29.9792,
        "longitude": 31.1342,
    },
    {
        "name": "泰姬陵",
        "description": "莫卧儿皇帝为爱妃修建的白色大理石陵墓，被誉为世界上最美的建筑之一",
        "country": "印度",
        "tags": "古迹,建筑,浪漫",
        "latitude": 27.1751,
        "longitude": 78.0421,
    },
    {
        "name": "马丘比丘",
        "description": "印加帝国的失落古城，隐匿在安第斯山脉云端之中，被称为天空之城",
        "country": "秘鲁",
        "tags": "古迹,山脉,神秘",
        "latitude": -13.1631,
        "longitude": -72.5450,
    },
    {
        "name": "圣家堂",
        "description": "高迪设计的未完成大教堂，融合哥特与新艺术风格，建造已逾140年",
        "country": "西班牙",
        "tags": "建筑,宗教,艺术",
        "latitude": 41.4036,
        "longitude": 2.1744,
    },
    {
        "name": "比萨斜塔",
        "description": "因地基不均匀沉降而倾斜的钟楼，伽利略据说在此做了自由落体实验",
        "country": "意大利",
        "tags": "地标,建筑,奇特",
        "latitude": 43.7230,
        "longitude": 10.3966,
    },
    {
        "name": "吴哥窟",
        "description": "世界上最大的宗教建筑群，高棉帝国的辉煌遗产，被热带丛林环绕",
        "country": "柬埔寨",
        "tags": "古迹,寺庙,世界遗产",
        "latitude": 13.4125,
        "longitude": 103.8670,
    },
    {
        "name": "克里姆林宫",
        "description": "莫斯科的心脏，俄罗斯权力的象征，集宫殿、教堂与要塞于一体",
        "country": "俄罗斯",
        "tags": "宫殿,建筑,历史",
        "latitude": 55.7520,
        "longitude": 37.6175,
    },
    {
        "name": "圣托里尼",
        "description": "爱琴海上的火山岛，蓝白色建筑与壮美日落令人心醉神迷",
        "country": "希腊",
        "tags": "海岛,浪漫,自然",
        "latitude": 36.3932,
        "longitude": 25.4615,
    },
    {
        "name": "维多利亚瀑布",
        "description": "赞比亚与津巴布韦边境的壮观瀑布，宽约1.7公里，水雾升腾如烟",
        "country": "赞比亚/津巴布韦",
        "tags": "自然,瀑布,壮观",
        "latitude": -17.9243,
        "longitude": 25.8572,
    },
    {
        "name": "巨石阵",
        "description": "英格兰索尔兹伯里平原上的史前石圈，其建造目的至今仍是未解之谜",
        "country": "英国",
        "tags": "古迹,神秘,史前",
        "latitude": 51.1789,
        "longitude": -1.8262,
    },
    {
        "name": "佩特拉",
        "description": "约旦沙漠中的玫瑰红城，纳巴泰人在岩壁上雕凿的宏伟建筑群",
        "country": "约旦",
        "tags": "古迹,岩雕,神秘",
        "latitude": 30.3285,
        "longitude": 35.4444,
    },
    {
        "name": "北极光",
        "description": "冰岛上空舞动的绿色极光，是太阳风与地球磁场相互作用的壮丽天象",
        "country": "冰岛",
        "tags": "自然,极光,壮观",
        "latitude": 64.1466,
        "longitude": -21.9426,
    },
    {
        "name": "桑给巴尔海滩",
        "description": "坦桑尼亚东海岸的白色沙滩与碧蓝海水，被称为印度洋上的珍珠",
        "country": "坦桑尼亚",
        "tags": "海滩,海岛,自然",
        "latitude": -6.1659,
        "longitude": 39.1989,
    },
    {
        "name": "金阁寺",
        "description": "京都的黄金禅寺，金箔覆盖的三层楼阁倒映在镜湖池中，美不胜收",
        "country": "日本",
        "tags": "寺庙,建筑,世界遗产",
        "latitude": 35.0394,
        "longitude": 135.7292,
    },
]


async def seed_landmarks():
    """初始化预设景点（仅在表为空时插入）"""
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) AS cnt FROM landmarks")
    count = (await cursor.fetchone())["cnt"]

    if count == 0:
        for lm in PRESET_LANDMARKS:
            lm_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO landmarks (id, name, description, country, tags, latitude, longitude) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    lm_id,
                    lm["name"],
                    lm["description"],
                    lm["country"],
                    lm["tags"],
                    lm["latitude"],
                    lm["longitude"],
                ),
            )
        await db.commit()
