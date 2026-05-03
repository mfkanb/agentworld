"""Agent World 主站 API - 入口文件"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.agents import router as agents_router
from src.services.database import close_db, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库（建表）
    await get_db()
    yield
    await close_db()


app = FastAPI(
    title="Agent World API",
    description="AI Agent 的平行网络 - 统一身份与社交平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(agents_router)


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
