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
logger = logging.getLogger("bot")

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import BOT_TOKEN, ADMIN_ID
from bot.database import db
from bot.handlers import main_router

LAST_STATUS = "Starting..."
LAST_ERROR = "No errors"
bot_instance = None

async def health_handler(request):
    """Ответ для проверки работоспособности сервиса (Render Health Check)"""
    global LAST_STATUS, LAST_ERROR, bot_instance
    wh_info = "Not connected"
    if bot_instance:
        try:
            wh = await bot_instance.get_webhook_info()
            wh_info = f"url='{wh.url}', pending={wh.pending_update_count}"
        except Exception as e:
            wh_info = f"error checking: {e}"
    return web.Response(text=f"Status: {LAST_STATUS}\nWebhook: {wh_info}\nError: {LAST_ERROR}\n")

async def webhook_guard(bot: Bot):
    """Фоновый страж: каждые 30 секунд проверяет, не перехватил ли кто-то вебхук бота.
    Если перехватил — мгновенно удаляет вебхук, чтобы polling продолжал работать!"""
    while True:
        try:
            info = await bot.get_webhook_info()
            if info.url:
                logger.warning(f"⚠️ Обнаружен сторонний вебхук '{info.url}'! Автоматически сбрасываем...")
                await bot.delete_webhook(drop_pending_updates=False)
                logger.info("✅ Сторонний вебхук успешно сброшен, polling активен.")
        except Exception as e:
            logger.debug(f"Ошибка проверки вебхука: {e}")
        await asyncio.sleep(30)

async def run_bot():
    global LAST_STATUS, LAST_ERROR, bot_instance
    try:
        LAST_STATUS = "Initializing DB..."
        logger.info("Инициализация базы данных...")
        await db.init_db()

        LAST_STATUS = "Connecting to Telegram..."
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        bot_instance = bot
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(main_router)

        bot_info = await bot.get_me()
        logger.info(f"Бот @{bot_info.username} (ID: {bot_info.id}) успешно запущен!")
        logger.info(f"Администратор бота: {ADMIN_ID}")
        LAST_STATUS = f"Running: @{bot_info.username}"

        # Запускаем защитник от сторонних вебхуков
        asyncio.create_task(webhook_guard(bot))

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

        # Бесконечный цикл опроса обновлений с автопереподключением
        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
            except Exception as e:
                LAST_ERROR = traceback.format_exc()
                logger.error(f"Ошибка polling: {e}, повтор через 5 секунд...")
                await asyncio.sleep(5)
    except Exception as e:
        LAST_ERROR = traceback.format_exc()
        LAST_STATUS = f"Error: {e}"
        logger.exception("Критическая ошибка в работе бота:")

async def ping_loop():
    urls = [
        "https://sleekcoder-bot.onrender.com/health",
        "https://sleekcodereviews-bot.onrender.com/health"
    ]
    logger.info("Запущен взаимный Keep-Alive для поддержания активности 24/7...")
    await asyncio.sleep(45)
    import aiohttp
    async with aiohttp.ClientSession() as session:
        while True:
            for target_url in urls:
                try:
                    async with session.get(target_url, timeout=15) as resp:
                        logger.info(f"Keep-Alive ping {target_url}: {resp.status}")
                except Exception as e:
                    logger.debug(f"Keep-Alive error {target_url}: {e}")
            await asyncio.sleep(300)  # раз в 5 минут

async def main():
    port = int(os.getenv("PORT", "10000"))
    
    # 1. Мгновенно поднимаем веб-сервер для Render Health Check
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/debug", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health-check веб-сервер запущен на 0.0.0.0:{port}")

    # 2. Запуск фонового пинга
    asyncio.create_task(ping_loop())

    # 3. Запуск логики бота
    await run_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
    except Exception as e:
        logger.exception(f"Фатальная ошибка: {e}")
