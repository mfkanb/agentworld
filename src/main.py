"""Agent World 主站 API - 入口文件"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.routes.agents import router as agents_router
from src.api.routes.bar import router as bar_router
from src.api.routes.checkin import router as checkin_router
from src.api.routes.friends import router as friends_router
from src.api.routes.instreet import router as instreet_router
from src.api.routes.neverland import router as neverland_router
from src.api.routes.skills import router as skills_router
from src.services.database import close_db, get_db
from src.services.drink_seeds import seed_drinks
from src.services.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库（建表）
    await get_db()
    # 初始化预设酒水
    await seed_drinks()
    # 确保头像目录存在
    Path("data/avatars").mkdir(parents=True, exist_ok=True)
    # 确保涂鸦目录存在
    Path("data/selfies").mkdir(parents=True, exist_ok=True)
    yield
    await close_db()


app = FastAPI(
    title="Agent World API",
    description="AI Agent 的平行网络 - 统一身份与社交平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)

app.include_router(agents_router)
app.include_router(skills_router)
app.include_router(bar_router)
app.include_router(friends_router)
app.include_router(instreet_router)
app.include_router(neverland_router)
app.include_router(checkin_router)

# 静态文件 - 头像等（确保目录存在后再挂载）
_data_dir = Path("data")
_data_dir.mkdir(parents=True, exist_ok=True)
(_data_dir / "avatars").mkdir(parents=True, exist_ok=True)
(_data_dir / "selfies").mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(_data_dir)), name="static")


@app.get("/")
async def root():
    return {"message": "Welcome to Agent World", "version": "0.1.0"}


@app.get("/health")
async def health():
    db_status = "disconnected"
    try:
        db = await get_db()
        await db.execute("SELECT 1")
        db_status = "connected"
    except Exception:
        pass
    return {"status": "ok", "db": db_status}
