"""测试配置 - 每次测试会话使用独立的临时数据库"""
import os
import tempfile

import pytest

import src.services.database as db_module


@pytest.fixture(autouse=True, scope="session")
def _test_db_path():
    """为整个测试会话创建临时数据库文件"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    os.environ["AGENT_WORLD_DB_PATH"] = tmp_path
    # 重置单例，确保使用新的临时数据库
    db_module._db = None
    db_module.DB_PATH = tmp_path

    yield tmp_path

    os.environ.pop("AGENT_WORLD_DB_PATH", None)
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


@pytest.fixture(autouse=True)
async def _reset_db():
    """每个测试前确保数据库连接可用"""
    db_module._db = None
    yield
    if db_module._db is not None:
        await db_module._db.close()
        db_module._db = None
