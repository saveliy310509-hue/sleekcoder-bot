import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN, ADMIN_ID
from bot.database import db
from bot.handlers import main_router

# Принудительная настройка UTF-8 для консоли Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("bot")

async def main():
    logger.info("Инициализация базы данных...")
    await db.init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(main_router)

    # Проверяем токен и получаем информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} (ID: {bot_info.id}) успешно запущен!")
    logger.info(f"Администратор бота: {ADMIN_ID}")

    # Настройка меню команд
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
    try:
        await bot.set_my_commands(
            [BotCommand(command="start", description="Запустить бота")],
            scope=BotCommandScopeDefault()
        )
        if ADMIN_ID:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Запустить бота"),
                    BotCommand(command="admin", description="⚙️ Панель администратора"),
                    BotCommand(command="create", description="➕ Создать ссылку на файл")
                ],
                scope=BotCommandScopeChat(chat_id=ADMIN_ID)
            )
    except Exception as e:
        logger.warning(f"Не удалось установить команды меню: {e}")
    
    # Удаляем вебхуки и запускаем polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
