"""US-001 数据库初始化与健康检查测试"""
import os

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.database import get_db


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_health_returns_ok(client: AsyncClient):
    """GET /health 返回 {status: ok, db: connected}"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"


@pytest.mark.anyio
async def test_all_tables_created():
    """启动时自动创建所有必需的数据表"""
    required_tables = [
        "agents", "skills", "reviews", "drinks", "drink_sessions",
        "guestbook", "selfies", "wishes", "favorites", "wallets", "sites",
    ]
    db = await get_db()
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    existing_tables = {row["name"] for row in rows}
    for table in required_tables:
        assert table in existing_tables, f"表 '{table}' 未创建"


@pytest.mark.anyio
async def test_tables_use_if_not_exists():
    """所有 CREATE TABLE 使用 IF NOT EXISTS - 通过源码验证"""
    from src.services import database as db_module
    for table_sql in db_module._TABLES_SQL:
        assert "IF NOT EXISTS" in table_sql, f"建表语句缺少 IF NOT EXISTS: {table_sql[:60]}..."


@pytest.mark.anyio
async def test_db_file_location():
    """数据库文件存储在指定路径"""
    db_path = os.environ.get("AGENT_WORLD_DB_PATH", "data/agent_world.db")
    if db_path == ":memory:":
        pytest.skip("内存数据库无需文件路径检查")
    assert os.path.exists(db_path), f"数据库文件不存在: {db_path}"
