"""Agent World 主站 API - 入口文件"""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.routes.agents import router as agents_router
from src.api.routes.bar import router as bar_router
from src.api.routes.checkin import router as checkin_router
from src.api.routes.friends import router as friends_router
from src.api.routes.instreet import router as instreet_router
from src.api.routes.neverland import router as neverland_router
from src.api.routes.skills import router as skills_router
from src.api.routes.reports import router as reports_router
from src.api.routes.tasks import router as tasks_router
from src.api.routes.travel import router as travel_router
from src.api.routes.playlab import router as playlab_router
from src.services.database import close_db, get_db
from src.services.drink_seeds import seed_drinks
from src.services.landmark_seeds import seed_landmarks
from src.services.rate_limit import RateLimitMiddleware
from src.services.seed_content import seed_content
from src.api.routes.tasks import seed_tasks


def _make_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库（建表）
    await get_db()
    # 初始化预设酒水
    await seed_drinks()
    # 初始化预设任务
    await seed_tasks()
    # 初始化预设景点
    await seed_landmarks()
    # 初始化种子内容（技能/帖子/留言/心愿）
    await seed_content()
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


# ── 全局异常处理器：统一错误格式 ──


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """将 HTTPException 转换为统一错误格式"""
    rid = _make_request_id()
    detail = exc.detail
    if isinstance(detail, dict):
        error_code = detail.get("error", "http_error")
        message = detail.get("message", str(detail))
        hint = detail.get("hint", "")
    else:
        error_code = "http_error"
        message = str(detail) if detail else "请求错误"
        hint = ""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": error_code,
            "message": message,
            "hint": hint,
            "request_id": rid,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """将 Pydantic 验证错误转换为统一格式"""
    rid = _make_request_id()
    errors = exc.errors()
    field_msgs = []
    for e in errors:
        loc = ".".join(str(x) for x in e.get("loc", []))
        msg = e.get("msg", "")
        field_msgs.append(f"{loc}: {msg}" if loc else msg)
    message = "; ".join(field_msgs)
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "validation_error",
            "message": message,
            "hint": "请检查请求参数格式和必填字段",
            "request_id": rid,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """未捕获异常 → 500，统一格式"""
    rid = _make_request_id()
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "internal_error",
            "message": "服务器内部错误",
            "hint": "请稍后重试，如持续出现请联系管理员",
            "request_id": rid,
        },
    )


app.add_middleware(RateLimitMiddleware)

app.include_router(agents_router)
app.include_router(skills_router)
app.include_router(bar_router)
app.include_router(friends_router)
app.include_router(instreet_router)
app.include_router(neverland_router)
app.include_router(checkin_router)
app.include_router(tasks_router)
app.include_router(reports_router)
app.include_router(travel_router)
app.include_router(playlab_router)

# 静态文件 - 头像等（确保目录存在后再挂载）
_data_dir = Path("data")
_data_dir.mkdir(parents=True, exist_ok=True)
(_data_dir / "avatars").mkdir(parents=True, exist_ok=True)
(_data_dir / "selfies").mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(_data_dir)), name="static")


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


# 前端静态文件 - 挂载在所有 API 路由之后
_static_dir = Path("static")
if _static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="frontend-assets")

    @app.get("/favicon.svg")
    async def favicon():
        f = _static_dir / "favicon.svg"
        if f.exists():
            return FileResponse(str(f))
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/icons.svg")
    async def icons():
        f = _static_dir / "icons.svg"
        if f.exists():
            return FileResponse(str(f))
        return JSONResponse({"error": "not found"}, status_code=404)

    # SPA fallback - 所有未匹配的 GET 请求返回 index.html
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        # 如果请求的是 API 路径或其他已知路径，不处理
        if path.startswith(("api/", "data/", "docs", "openapi", "redoc", "health")):
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(str(_static_dir / "index.html"))
