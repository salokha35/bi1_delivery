# storage.py

import aiosqlite

DB_NAME = "sessions.db"


async def init_db():
    """
    Инициализация базы данных: создаёт таблицу sessions, если её нет.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                telegram_id INTEGER PRIMARY KEY,
                access_token TEXT NOT NULL
            )
        """)
        await db.commit()


async def save_token(telegram_id: int, access_token: str):
    """
    Сохраняет токен для пользователя.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO sessions (telegram_id, access_token)
            VALUES (?, ?)
        """, (telegram_id, access_token))
        await db.commit()


async def get_token(telegram_id: int) -> str | None:
    """
    Возвращает токен по Telegram ID, если он существует.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT access_token FROM sessions WHERE telegram_id = ?
        """, (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def delete_token(telegram_id: int):
    """
    Удаляет токен пользователя (logout).
    """
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            DELETE FROM sessions WHERE telegram_id = ?
        """, (telegram_id,))
        await db.commit()
