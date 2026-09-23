import asyncio
import logging
import os
import sys
import traceback
from aiohttp import web

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
logger = logging.getLogger("unified_bot")

# Добавляем путь к reviews_bot для корректного импорта внутренних модулей
reviews_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "reviews_bot"))
if reviews_path not in sys.path:
    sys.path.insert(0, reviews_path)

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

# Импорт бота скачивания файлов
from bot.config import BOT_TOKEN as FILES_BOT_TOKEN, ADMIN_ID as FILES_ADMIN_ID
from bot.database import db as files_db
from bot.handlers import main_router as files_router

# Импорт бота отзывов
import reviews_bot.engine as reviews_bot_module
import reviews_bot.config as reviews_config_module

BOT1_STATUS = "Starting..."
BOT1_ERROR = "No errors"
bot1_instance = None

BOT2_STATUS = "Starting..."
BOT2_ERROR = "No errors"
bot2_instance = None

async def health_handler(request):
    """Ответ для проверки работоспособности сервиса (Render Health Check)"""
    global BOT1_STATUS, BOT1_ERROR, bot1_instance
    global BOT2_STATUS, BOT2_ERROR, bot2_instance

    wh1_info = "Not connected"
    if bot1_instance:
        try:
            wh = await bot1_instance.get_webhook_info()
            wh1_info = f"url='{wh.url}', pending={wh.pending_update_count}"
        except Exception as e:
            wh1_info = f"error: {e}"

    wh2_info = "Not connected"
    b2 = bot2_instance or reviews_bot_module.bot_instance
    if b2:
        try:
            wh = await b2.get_webhook_info()
            wh2_info = f"url='{wh.url}', pending={wh.pending_update_count}"
        except Exception as e:
            wh2_info = f"error: {e}"

    b2_status = reviews_bot_module.LAST_STATUS or BOT2_STATUS
    b2_error = reviews_bot_module.LAST_ERROR or BOT2_ERROR

    body = (
        f"=== Bot 1 (@sleekcoder_bot - Files) ===\n"
        f"Status: {BOT1_STATUS}\n"
        f"Webhook: {wh1_info}\n"
        f"Error: {BOT1_ERROR}\n\n"
        f"=== Bot 2 (@sleekcodereviews_bot - Reviews) ===\n"
        f"Status: {b2_status}\n"
        f"Webhook: {wh2_info}\n"
        f"Error: {b2_error}\n"
    )
    return web.Response(text=body)

async def webhook_guard(bot: Bot, bot_name: str):
    """Фоновый страж: каждые 30 секунд проверяет и сбрасывает любые сторонние вебхуки."""
    while True:
        try:
            info = await bot.get_webhook_info()
            if info.url:
                logger.warning(f"⚠️ [{bot_name}] Обнаружен сторонний вебхук '{info.url}'! Автоматически сбрасываем...")
                await bot.delete_webhook(drop_pending_updates=False)
                logger.info(f"✅ [{bot_name}] Сторонний вебхук сброшен, polling активен.")
        except Exception as e:
            logger.debug(f"[{bot_name}] Ошибка проверки вебхука: {e}")
        await asyncio.sleep(30)

async def run_files_bot():
    """Запуск бота скачивания файлов (@sleekcoder_bot)"""
    global BOT1_STATUS, BOT1_ERROR, bot1_instance
    try:
        BOT1_STATUS = "Initializing DB..."
        logger.info("[Bot 1 Files] Инициализация базы данных...")
        await files_db.init_db()

        BOT1_STATUS = "Connecting to Telegram..."
        bot = Bot(
            token=FILES_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        bot1_instance = bot
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(files_router)

        bot_info = await bot.get_me()
        logger.info(f"[Bot 1 Files] Бот @{bot_info.username} (ID: {bot_info.id}) запущен!")
        BOT1_STATUS = f"Running: @{bot_info.username}"

        asyncio.create_task(webhook_guard(bot, "FilesBot"))

        from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description="Запустить бота")],
                scope=BotCommandScopeDefault()
            )
            if FILES_ADMIN_ID:
                await bot.set_my_commands(
                    [
                        BotCommand(command="start", description="Запустить бота"),
                        BotCommand(command="admin", description="⚙️ Панель администратора"),
                        BotCommand(command="create", description="➕ Создать ссылку на файл")
                    ],
                    scope=BotCommandScopeChat(chat_id=FILES_ADMIN_ID)
                )
        except Exception as e:
            logger.warning(f"[Bot 1 Files] Ошибка меню команд: {e}")

        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
            except Exception as e:
                BOT1_ERROR = traceback.format_exc()
                logger.error(f"[Bot 1 Files] Ошибка polling: {e}, повтор через 5 секунд...")
                await asyncio.sleep(5)
    except Exception as e:
        BOT1_ERROR = traceback.format_exc()
        BOT1_STATUS = f"Error: {e}"
        logger.exception("[Bot 1 Files] Критическая ошибка:")

async def run_reviews_bot():
    """Запуск бота отзывов (@sleekcodereviews_bot)"""
    global BOT2_STATUS, BOT2_ERROR, bot2_instance
    try:
        BOT2_STATUS = "Loading config..."
        logger.info("[Bot 2 Reviews] Загрузка конфигурации...")
        config = reviews_config_module.load_config()

        logger.info("[Bot 2 Reviews] Инициализация бота и БД...")
        bot, dp, db = reviews_bot_module.create_bot_and_dispatcher(config)
        bot2_instance = bot
        reviews_bot_module.bot_instance = bot

        bot_info = await bot.get_me()
        logger.info(f"[Bot 2 Reviews] Бот @{bot_info.username} (ID: {bot_info.id}) запущен!")
        BOT2_STATUS = f"Running: @{bot_info.username}"
        reviews_bot_module.LAST_STATUS = BOT2_STATUS

        asyncio.create_task(webhook_guard(bot, "ReviewsBot"))

        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            except Exception as e:
                BOT2_ERROR = traceback.format_exc()
                reviews_bot_module.LAST_ERROR = BOT2_ERROR
                logger.error(f"[Bot 2 Reviews] Ошибка polling: {e}, повтор через 5 секунд...")
                await asyncio.sleep(5)
    except Exception as e:
        BOT2_ERROR = traceback.format_exc()
        BOT2_STATUS = f"Error: {e}"
        reviews_bot_module.LAST_ERROR = BOT2_ERROR
        reviews_bot_module.LAST_STATUS = BOT2_STATUS
        logger.exception("[Bot 2 Reviews] Критическая ошибка:")

async def ping_loop():
    """24/7 Keep-Alive пинг, чтобы Render никогда не засыпал"""
    url = os.getenv("RENDER_EXTERNAL_URL", "https://sleekcoder-bot.onrender.com/health")
    logger.info(f"Запущен Keep-Alive для {url} (интервал: 5 минут)")
    await asyncio.sleep(45)
    import aiohttp
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(url, timeout=15) as resp:
                    logger.info(f"Keep-Alive ping {url}: {resp.status}")
            except Exception as e:
                logger.debug(f"Keep-Alive ping error: {e}")
            await asyncio.sleep(300)

async def main():
    port = int(os.getenv("PORT", "10000"))
    
    # 1. Запуск Health-check веб-сервера
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/debug", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Unified Health-Check сервер запущен на 0.0.0.0:{port}")

    # 2. Запуск фонового пингера Keep-Alive
    asyncio.create_task(ping_loop())

    # 3. Запуск обоих ботов параллельно
    task_files = asyncio.create_task(run_files_bot())
    task_reviews = asyncio.create_task(run_reviews_bot())

    await asyncio.gather(task_files, task_reviews)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Сервис остановлен.")
    except Exception as e:
        logger.exception(f"Фатальная ошибка: {e}")
