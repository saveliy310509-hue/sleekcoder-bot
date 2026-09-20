import aiosqlite
from typing import Optional, List, Dict, Any
from bot.config import DB_PATH

DEFAULT_TEXTS = [
    (
        "welcome_default",
        "Приветствие пользователя (/start без ссылки)",
        "👋 <b>Добро пожаловать!</b>\n\nЭтот бот предназначен для скачивания файлов и плагинов по специальным ссылкам."
    ),
    (
        "file_caption_default",
        "Стандартная подпись к файлу",
        "📦 <b>{name}</b>\n📥 Скачиваний: <b>{downloads}</b>\n\nВаш файл готов к скачиванию!"
    ),
    (
        "file_delivery_text",
        "Сообщение перед отправкой файла",
        "🚀 <b>Отправляем файл...</b>"
    ),
    (
        "link_not_found",
        "Ошибка: ссылка не найдена",
        "❌ <b>Ссылка не найдена или устарела.</b>\n\nПроверьте правильность ссылки."
    ),
    (
        "admin_welcome",
        "Приветствие администратора",
        "👑 <b>Панель управления ботом</b>\n\nЗдесь вы можете управлять ссылками, настраивать тексты и смотреть статистику."
    )
]

async def init_db():
    """Инициализация таблиц базы данных и дефолтных текстов"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_unique_id TEXT,
                file_type TEXT NOT NULL,
                caption TEXT,
                clicks INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_texts (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                value TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Вставляем дефолтные тексты, если их еще нет
        for key, title, val in DEFAULT_TEXTS:
            await db.execute("""
                INSERT OR IGNORE INTO bot_texts (key, title, value)
                VALUES (?, ?, ?)
            """, (key, title, val))

        await db.commit()

# --- Пользователи и статистика ---

async def add_or_update_user(user_id: int, username: Optional[str], first_name: Optional[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        await db.commit()

async def get_stats() -> Dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as cnt FROM users") as cursor:
            row = await cursor.fetchone()
            total_users = row["cnt"] if row else 0

        async with db.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(clicks), 0) as total_clicks FROM links") as cursor:
            row = await cursor.fetchone()
            total_links = row["cnt"] if row else 0
            total_downloads = row["total_clicks"] if row else 0

        return {
            "total_users": total_users,
            "total_links": total_links,
            "total_downloads": total_downloads
        }

# --- Ссылки ---

async def create_link(code: str, name: str, file_id: str, file_unique_id: Optional[str], file_type: str, caption: Optional[str] = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO links (code, name, file_id, file_unique_id, file_type, caption)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, name, file_id, file_unique_id, file_type, caption))
        await db.commit()
        return cursor.lastrowid

async def get_link_by_code(code: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM links WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_link_by_id(link_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM links WHERE id = ?", (link_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def increment_link_clicks(code: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE links SET clicks = clicks + 1 WHERE code = ?", (code,))
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT clicks FROM links WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            return row["clicks"] if row else 1

async def count_links() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM links") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_links_paginated(limit: int = 5, offset: int = 0) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM links
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def delete_link(link_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM links WHERE id = ?", (link_id,))
        await db.commit()
        return cursor.rowcount > 0

async def update_link_file(link_id: int, file_id: str, file_unique_id: Optional[str], file_type: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE links
            SET file_id = ?, file_unique_id = ?, file_type = ?
            WHERE id = ?
        """, (file_id, file_unique_id, file_type, link_id))
        await db.commit()
        return cursor.rowcount > 0

async def update_link_caption(link_id: int, caption: Optional[str]) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE links
            SET caption = ?
            WHERE id = ?
        """, (caption, link_id))
        await db.commit()
        return cursor.rowcount > 0

async def update_link_name(link_id: int, name: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE links
            SET name = ?
            WHERE id = ?
        """, (name, link_id))
        await db.commit()
        return cursor.rowcount > 0

# --- Тексты сообщений ---

async def get_all_texts() -> List[Dict[str, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, title, value FROM bot_texts ORDER BY key") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_text(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT value FROM bot_texts WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row and row["value"]:
                return row["value"]
            return default

async def update_text(key: str, value: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE bot_texts SET value = ? WHERE key = ?", (value, key))
        await db.commit()
        return cursor.rowcount > 0

async def get_text_item(key: str) -> Optional[Dict[str, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, title, value FROM bot_texts WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
