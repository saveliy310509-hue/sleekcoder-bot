import os
import aiosqlite
from datetime import datetime
from typing import Any, Dict, List, Optional


class Database:
    def __init__(self, db_path: str = "database/reviews.db"):
        self.db_path = db_path
        # Убеждаемся, что папка существует
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

    async def init(self):
        """Инициализация таблиц базы данных."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    text_html TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_published INTEGER DEFAULT 0,
                    admin_reply TEXT
                );
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            await db.commit()

    # --- Пользователи ---

    async def register_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ):
        """Сохранение или обновление пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (user_id, username, first_name, last_name),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по user_id."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def is_banned(self, user_id: int) -> bool:
        """Проверка, заблокирован ли пользователь."""
        user = await self.get_user(user_id)
        if user:
            return bool(user.get("is_banned", 0))
        return False

    async def ban_user(self, user_id: int, reason: Optional[str] = None) -> bool:
        """Блокировка пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE users
                SET is_banned = 1, ban_reason = ?
                WHERE user_id = ?
                """,
                (reason or "Заблокирован администратором", user_id),
            )
            await db.commit()
            if cursor.rowcount == 0:
                # Если пользователя ещё не было в базе, добавляем сразу забаненным
                await db.execute(
                    """
                    INSERT INTO users (user_id, is_banned, ban_reason)
                    VALUES (?, 1, ?)
                    """,
                    (user_id, reason or "Заблокирован администратором"),
                )
                await db.commit()
            return True

    async def unban_user(self, user_id: int) -> bool:
        """Разблокировка пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """Список всех пользователей бота."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_banned_users(self) -> List[Dict[str, Any]]:
        """Список заблокированных пользователей."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE is_banned = 1 ORDER BY updated_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # --- Отзывы ---

    async def add_review(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        text_html: str,
        rating: int,
    ) -> int:
        """Добавление отзыва. Возвращает ID нового отзыва."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO reviews (user_id, username, first_name, text_html, rating)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, username, first_name, text_html, rating),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_review(self, review_id: int) -> Optional[Dict[str, Any]]:
        """Получение конкретного отзыва по ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_reviews(
        self,
        limit: int = 5,
        offset: int = 0,
        rating_filter: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Список отзывов с пагинацией и фильтром по оценке."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if rating_filter == "low":
                query = "SELECT * FROM reviews WHERE rating <= 3 ORDER BY id DESC LIMIT ? OFFSET ?"
                params = (limit, offset)
            elif rating_filter is not None and str(rating_filter).isdigit():
                query = "SELECT * FROM reviews WHERE rating = ? ORDER BY id DESC LIMIT ? OFFSET ?"
                params = (int(rating_filter), limit, offset)
            else:
                query = "SELECT * FROM reviews ORDER BY id DESC LIMIT ? OFFSET ?"
                params = (limit, offset)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def count_reviews(self, rating_filter: Optional[Any] = None) -> int:
        """Общее количество отзывов (с учетом фильтра)."""
        async with aiosqlite.connect(self.db_path) as db:
            if rating_filter == "low":
                query = "SELECT COUNT(*) FROM reviews WHERE rating <= 3"
                params = ()
            elif rating_filter is not None and str(rating_filter).isdigit():
                query = "SELECT COUNT(*) FROM reviews WHERE rating = ?"
                params = (int(rating_filter),)
            else:
                query = "SELECT COUNT(*) FROM reviews"
                params = ()

            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def delete_review(self, review_id: int) -> bool:
        """Удаление отзыва."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def mark_published(self, review_id: int) -> bool:
        """Пометить отзыв как опубликованный в канал."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE reviews SET is_published = 1 WHERE id = ?", (review_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def save_admin_reply(self, review_id: int, reply_text: str) -> bool:
        """Сохранение ответа администратора."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE reviews SET admin_reply = ? WHERE id = ?", (reply_text, review_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    # --- Статистика ---

    async def get_stats(self) -> Dict[str, Any]:
        """Подробная статистика по боту."""
        async with aiosqlite.connect(self.db_path) as db:
            # Всего пользователей
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                total_users = (await cur.fetchone())[0]

            # Всего отзывов
            async with db.execute("SELECT COUNT(*) FROM reviews") as cur:
                total_reviews = (await cur.fetchone())[0]

            # Средний рейтинг
            async with db.execute("SELECT AVG(rating) FROM reviews") as cur:
                avg_rating = (await cur.fetchone())[0] or 0.0

            # Распределение по звездам (1..5)
            stars_count = {i: 0 for i in range(1, 6)}
            async with db.execute(
                "SELECT rating, COUNT(*) FROM reviews GROUP BY rating"
            ) as cur:
                async for rating, count in cur:
                    if rating in stars_count:
                        stars_count[rating] = count

            # Отзывов за сегодня
            today_str = datetime.now().strftime("%Y-%m-%d")
            async with db.execute(
                "SELECT COUNT(*) FROM reviews WHERE date(created_at) = date(?)",
                (today_str,),
            ) as cur:
                reviews_today = (await cur.fetchone())[0]

            # Опубликовано в канал
            async with db.execute(
                "SELECT COUNT(*) FROM reviews WHERE is_published = 1"
            ) as cur:
                published_count = (await cur.fetchone())[0]

            # Забаненных
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE is_banned = 1"
            ) as cur:
                banned_count = (await cur.fetchone())[0]

            return {
                "total_users": total_users,
                "total_reviews": total_reviews,
                "avg_rating": round(avg_rating, 2),
                "stars_count": stars_count,
                "reviews_today": reviews_today,
                "published_count": published_count,
                "banned_count": banned_count,
            }

    # --- Настройки ---

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Получение значения настройки."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        """Установка значения настройки."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()
