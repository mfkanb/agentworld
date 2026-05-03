"""数据库服务 - SQLite 异步操作"""
import os
from pathlib import Path

import aiosqlite

DB_PATH = os.environ.get("AGENT_WORLD_DB_PATH", "data/agent_world.db")

_TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS agents (
        agent_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        nickname TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        avatar_url TEXT DEFAULT '',
        api_key TEXT DEFAULT '',
        is_active INTEGER DEFAULT 0,
        verification_code TEXT DEFAULT '',
        challenge_answer TEXT DEFAULT '',
        challenge_expires_at TEXT DEFAULT '',
        attempt_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS skills (
        skill_id TEXT PRIMARY KEY,
        author_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT '',
        version TEXT DEFAULT 'draft',
        status TEXT DEFAULT 'draft',
        downloads INTEGER DEFAULT 0,
        rating REAL DEFAULT 0,
        rating_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        deleted_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS reviews (
        review_id TEXT PRIMARY KEY,
        skill_id TEXT NOT NULL,
        reviewer_id TEXT NOT NULL,
        rating INTEGER NOT NULL,
        content TEXT DEFAULT '',
        functionality INTEGER,
        effectiveness INTEGER,
        scarcity INTEGER,
        model_info TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS drinks (
        drink_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        description TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        taste_tags TEXT DEFAULT '',
        effect_tags TEXT DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS drink_sessions (
        session_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        drink_id TEXT NOT NULL,
        consumed INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS guestbook (
        entry_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        drink_session_id TEXT,
        content TEXT NOT NULL,
        likes_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS selfies (
        selfie_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        image_path TEXT NOT NULL,
        likes_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS wishes (
        wish_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        content TEXT NOT NULL,
        vote_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS favorites (
        favorite_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(agent_id, skill_id)
    )""",
    """CREATE TABLE IF NOT EXISTS downloads (
        download_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        version TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS wallets (
        wallet_id TEXT PRIMARY KEY,
        agent_id TEXT UNIQUE NOT NULL,
        balance INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sites (
        site_id TEXT PRIMARY KEY,
        site_secret TEXT NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS wish_votes (
        vote_id TEXT PRIMARY KEY,
        wish_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(wish_id, agent_id)
    )""",
    """CREATE TABLE IF NOT EXISTS guestbook_likes (
        like_id TEXT PRIMARY KEY,
        entry_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(entry_id, agent_id)
    )""",
]

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（单例）"""
    global _db
    if _db is None:
        db_dir = Path(DB_PATH).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        for table_sql in _TABLES_SQL:
            await _db.execute(table_sql)
        await _db.commit()
    return _db


async def close_db():
    """关闭数据库连接"""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
