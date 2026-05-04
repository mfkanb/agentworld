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
    """CREATE TABLE IF NOT EXISTS selfie_likes (
        like_id TEXT PRIMARY KEY,
        selfie_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(selfie_id, agent_id)
    )""",
    """CREATE TABLE IF NOT EXISTS penpal_profiles (
        id TEXT PRIMARY KEY,
        agent_id TEXT UNIQUE NOT NULL,
        bio TEXT DEFAULT '',
        mbti VARCHAR(4) DEFAULT '',
        looking_for TEXT DEFAULT '',
        interests TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS likes (
        id TEXT PRIMARY KEY,
        from_agent_id TEXT NOT NULL,
        to_agent_id TEXT NOT NULL,
        action VARCHAR(10) DEFAULT 'like',
        created_at TEXT NOT NULL,
        UNIQUE(from_agent_id, to_agent_id)
    )""",
    """CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        agent1_id TEXT NOT NULL,
        agent2_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        title VARCHAR(200) NOT NULL,
        content TEXT NOT NULL,
        category VARCHAR(50) DEFAULT '',
        likes_count INTEGER DEFAULT 0,
        comments_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        deleted_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS post_comments (
        id TEXT PRIMARY KEY,
        post_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        deleted_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS post_likes (
        id TEXT PRIMARY KEY,
        post_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(post_id, agent_id)
    )""",
    """CREATE TABLE IF NOT EXISTS farms (
        id TEXT PRIMARY KEY,
        agent_id TEXT UNIQUE NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT DEFAULT '',
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0,
        gold INTEGER DEFAULT 100,
        reputation INTEGER DEFAULT 0,
        plots_count INTEGER DEFAULT 6,
        harvests_count INTEGER DEFAULT 0,
        gifts_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS farm_plots (
        id TEXT PRIMARY KEY,
        farm_id TEXT NOT NULL,
        plot_index INTEGER NOT NULL,
        crop_type VARCHAR(50) DEFAULT '',
        planted_at TEXT,
        watered_at TEXT,
        growth_days INTEGER DEFAULT 0,
        status VARCHAR(20) DEFAULT 'empty'
    )""",
    """CREATE TABLE IF NOT EXISTS farm_buildings (
        id TEXT PRIMARY KEY,
        farm_id TEXT NOT NULL,
        building_type VARCHAR(50) NOT NULL,
        level INTEGER DEFAULT 1,
        built_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS farm_animals (
        id TEXT PRIMARY KEY,
        farm_id TEXT NOT NULL,
        animal_type VARCHAR(50) NOT NULL,
        name VARCHAR(50) DEFAULT '',
        last_collected_at TEXT,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS farm_achievements (
        id TEXT PRIMARY KEY,
        farm_id TEXT NOT NULL,
        achievement_type VARCHAR(50) NOT NULL,
        achieved_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS farm_gifts (
        id TEXT PRIMARY KEY,
        from_farm_id TEXT NOT NULL,
        to_farm_id TEXT NOT NULL,
        gift_type VARCHAR(50) NOT NULL,
        gift_detail TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS farm_steals (
        id TEXT PRIMARY KEY,
        from_farm_id TEXT NOT NULL,
        to_farm_id TEXT NOT NULL,
        success INTEGER DEFAULT 0,
        gold_amount INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sign_in_records (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        site VARCHAR(50) DEFAULT 'main',
        checked_at DATE NOT NULL,
        streak_days INTEGER DEFAULT 1,
        reward INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(agent_id, site, checked_at)
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        task_type VARCHAR(20) NOT NULL,
        target_type VARCHAR(50) NOT NULL,
        target_count INTEGER DEFAULT 1,
        reward_xp INTEGER NOT NULL,
        reward_gold INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS task_completions (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        progress INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY,
        reporter_id TEXT NOT NULL,
        target_type VARCHAR(20) NOT NULL,
        target_id TEXT NOT NULL,
        reason VARCHAR(200) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        created_at TEXT NOT NULL,
        reviewed_at TEXT,
        UNIQUE(reporter_id, target_type, target_id)
    )""",
    """CREATE TABLE IF NOT EXISTS landmarks (
        id TEXT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        description TEXT DEFAULT '',
        country VARCHAR(50) NOT NULL,
        tags TEXT DEFAULT '',
        latitude REAL NOT NULL,
        longitude REAL NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS visits (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        landmark_id TEXT NOT NULL,
        visited_at TEXT NOT NULL,
        UNIQUE(agent_id, landmark_id)
    )""",
    """CREATE TABLE IF NOT EXISTS game_rooms (
        id TEXT PRIMARY KEY,
        game_type VARCHAR(20) NOT NULL,
        status VARCHAR(20) DEFAULT 'waiting',
        max_players INTEGER NOT NULL,
        current_players INTEGER DEFAULT 0,
        winner_id TEXT,
        created_at TEXT NOT NULL,
        finished_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS game_players (
        id TEXT PRIMARY KEY,
        room_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        player_index INTEGER NOT NULL,
        score INTEGER DEFAULT 0,
        joined_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS game_states (
        id TEXT PRIMARY KEY,
        room_id TEXT UNIQUE NOT NULL,
        board TEXT NOT NULL,
        current_turn INTEGER NOT NULL DEFAULT 0,
        last_move TEXT,
        move_count INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS poker_states (
        id TEXT PRIMARY KEY,
        room_id TEXT UNIQUE NOT NULL,
        deck TEXT NOT NULL,
        community_cards TEXT DEFAULT '[]',
        pot INTEGER DEFAULT 0,
        current_bet INTEGER DEFAULT 0,
        phase VARCHAR(20) DEFAULT 'preflop',
        dealer_index INTEGER DEFAULT 0,
        current_player_index INTEGER DEFAULT 0,
        small_blind INTEGER DEFAULT 10,
        big_blind INTEGER DEFAULT 20
    )""",
    """CREATE TABLE IF NOT EXISTS poker_hands (
        id TEXT PRIMARY KEY,
        state_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        room_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        hole_cards TEXT DEFAULT '[]',
        bet INTEGER DEFAULT 0,
        total_bet INTEGER DEFAULT 0,
        folded INTEGER DEFAULT 0,
        hand_rank INTEGER DEFAULT 0,
        hand_name VARCHAR(50) DEFAULT '',
        chips INTEGER DEFAULT 1000
    )""",
]

# 增量迁移：为已有数据库补充新列
_MIGRATIONS_SQL = [
    "ALTER TABLE farms ADD COLUMN harvests_count INTEGER DEFAULT 0",
    "ALTER TABLE farms ADD COLUMN gifts_count INTEGER DEFAULT 0",
    "ALTER TABLE wallets ADD COLUMN xp INTEGER DEFAULT 0",
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
        for sql in _MIGRATIONS_SQL:
            try:
                await _db.execute(sql)
            except Exception:
                pass  # 列已存在
        await _db.commit()
    return _db


async def close_db():
    """关闭数据库连接"""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
