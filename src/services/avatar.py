"""头像服务 - 默认头像生成与上传处理"""
import os
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

# 头像存储目录
AVATAR_DIR = Path("data/avatars")

# 允许的图片格式及其 MIME 类型
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# 最大文件大小 5MB
MAX_FILE_SIZE = 5 * 1024 * 1024


def generate_default_avatar(agent_id: str) -> str:
    """使用 Pillow 生成抽象图案默认头像，返回文件相对路径"""
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    img_size = 200
    img = Image.new("RGB", (img_size, img_size))
    draw = ImageDraw.Draw(img)

    # 使用 agent_id 作为随机种子，确保每个 agent 头像独特
    import random
    seed = int(uuid.UUID(agent_id).int % (2**32))
    rng = random.Random(seed)

    # 随机背景色
    bg_color = (rng.randint(30, 200), rng.randint(30, 200), rng.randint(30, 200))
    img.paste(bg_color, [0, 0, img_size, img_size])

    # 绘制抽象图案：随机圆形和矩形
    for _ in range(rng.randint(5, 15)):
        shape_type = rng.choice(["circle", "rect"])
        color = (rng.randint(50, 255), rng.randint(50, 255), rng.randint(50, 255))
        alpha_color = (
            color[0],
            color[1],
            color[2],
            rng.randint(80, 180),
        )

        overlay = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        if shape_type == "circle":
            x1, y1 = rng.randint(0, img_size), rng.randint(0, img_size)
            radius = rng.randint(10, 60)
            overlay_draw.ellipse(
                [x1 - radius, y1 - radius, x1 + radius, y1 + radius],
                fill=alpha_color,
            )
        else:
            x1, y1 = rng.randint(0, img_size), rng.randint(0, img_size)
            w, h = rng.randint(20, 80), rng.randint(20, 80)
            overlay_draw.rectangle([x1, y1, x1 + w, y1 + h], fill=alpha_color)

        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    filename = f"{agent_id}_default.png"
    filepath = AVATAR_DIR / filename
    img.save(filepath, "PNG")

    return f"/data/avatars/{filename}"


def get_avatar_path(agent_id: str, ext: str) -> Path:
    """获取头像文件保存路径"""
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{agent_id}.{ext}"
    return AVATAR_DIR / filename
