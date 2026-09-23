import asyncio
import logging
import os
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import Config, load_config
from database.db import Database
from handlers import admin_router, user_router
from handlers.errors import global_error_handler
from middlewares import ThrottlingMiddleware

# Настройка красивого логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SleekCodeBot")


def setup_sentry(config: Config):
    """Инициализация мониторинга Sentry / GlitchTip (если указан SENTRY_DSN)."""
    if not config.sentry_dsn:
        logger.info("Sentry DSN не задан. Мониторинг Sentry отключен.")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.aiohttp import AioHttpIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        )

        sentry_sdk.init(
            dsn=config.sentry_dsn,
            integrations=[sentry_logging, AioHttpIntegration()],
            traces_sample_rate=1.0,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        logger.info("Sentry / GlitchTip успешно инициализирован.")
    except Exception as e:
        logger.warning("Не удалось инициализировать Sentry: %s", e)


async def setup_bot_commands(bot: Bot):
    """Установка списка команд в меню Telegram (скрываем команду /admin из подсказок)."""
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота / Главное меню"),
        BotCommand(command="review", description="✍️ Оставить отзыв"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def on_startup(bot: Bot, dp: Dispatcher, config: Config, db: Database):
    """Общие действия при старте бота (как для polling, так и для webhook)."""
    await db.init()
    logger.info("База данных SQLite успешно инициализирована: %s", config.db_path)

    try:
        await setup_bot_commands(bot)
    except Exception as e:
        logger.warning("Не удалось установить команды бота: %s", e)

    bot_info = await bot.get_me()
    logger.info("Бот успешно инициализирован: @%s (ID: %s)", bot_info.username, bot_info.id)
    logger.info("Режим работы: %s", config.bot_mode.upper())
    logger.info("Администраторы: %s", config.admin_ids)

    if config.bot_mode == "webhook":
        if not config.webhook_url:
            raise ValueError(
                "Ошибка: переменная WEBHOOK_URL не указана в .env файле для режима webhook!"
            )
        webhook_full_url = f"{config.webhook_url.rstrip('/')}{config.webhook_path}"
        await bot.set_webhook(
            url=webhook_full_url,
            secret_token=config.webhook_secret_token,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
        logger.info("Вебхук Telegram успешно установлен: %s", webhook_full_url)


async def on_shutdown(bot: Bot, config: Config):
    """Общие действия при остановке бота."""
    if config.bot_mode == "webhook":
        try:
            await bot.delete_webhook()
            logger.info("Вебхук Telegram успешно удален.")
        except Exception as e:
            logger.warning("Ошибка при удалении вебхука: %s", e)

    if not bot.session.closed:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


def create_bot_and_dispatcher(config: Config):
    """Создание и связывание компонентов Bot, Dispatcher, Middleware и Router."""
    # 1. Мониторинг Sentry / GlitchTip
    setup_sentry(config)

    # 2. Инициализация базы данных
    db = Database(config.db_path)

    # 3. Создание экземпляра бота с HTML режимом по умолчанию
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # 4. Диспетчер
    dp = Dispatcher(storage=MemoryStorage())

    # Пробрасываем зависимости в хэндлеры
    dp["config"] = config
    dp["db"] = db

    # 5. Подключение Rate Limiting & Throttling Middleware
    throttling_middleware = ThrottlingMiddleware(rate_limit=config.rate_limit_seconds)
    dp.message.middleware(throttling_middleware)
    dp.callback_query.middleware(throttling_middleware)
    logger.info("Throttling Middleware подключен (лимит: %.2f сек).", config.rate_limit_seconds)

    # 6. Подключение глобального обработчика ошибок с алертами админам
    dp.error.register(global_error_handler)
    logger.info("Глобальный обработчик ошибок с отправкой алертов в Telegram подключен.")

    # 7. Подключение роутеров
    dp.include_router(admin_router)
    dp.include_router(user_router)

    # 8. Регистрация хуков жизненного цикла
    async def _startup_wrapper():
        await on_startup(bot=bot, dp=dp, config=config, db=db)

    async def _shutdown_wrapper():
        await on_shutdown(bot=bot, config=config)

    dp.startup.register(_startup_wrapper)
    dp.shutdown.register(_shutdown_wrapper)

    return bot, dp, db


def run_webhook_mode(bot: Bot, dp: Dispatcher, config: Config):
    """Запуск бота в режиме Webhook через встроенный aiohttp веб-сервер."""
    app = web.Application()

    # Healthcheck эндпоинты для Nginx, Caddy, Docker
    async def healthcheck(request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "service": "sleekcode-reviews-bot",
            "mode": "webhook",
        })

    app.router.add_get("/health", healthcheck)
    app.router.add_get("/ping", healthcheck)

    # Обработчик входящих запросов от Telegram
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.webhook_secret_token,
    ).register(app, path=config.webhook_path)

    setup_application(app, dp, bot=bot)

    logger.info(
        "Запуск веб-сервера на %s:%s (путь: %s)",
        config.webapp_host,
        config.webapp_port,
        config.webhook_path,
    )
    web.run_app(app, host=config.webapp_host, port=config.webapp_port)


LAST_STATUS = "Starting..."
LAST_ERROR = "No errors"
bot_instance = None

async def health_handler(request: web.Request) -> web.Response:
    """Ответ для Render Health Check"""
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

async def run_bot_polling(config: Config):
    global LAST_STATUS, LAST_ERROR, bot_instance
    try:
        LAST_STATUS = "Initializing components..."
        bot, dp, db = create_bot_and_dispatcher(config)
        bot_instance = bot
        bot_info = await bot.get_me()
        logger.info("Бот успешно запущен: @%s (ID: %s)", bot_info.username, bot_info.id)
        LAST_STATUS = f"Running: @{bot_info.username}"

        asyncio.create_task(webhook_guard(bot))

        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            except Exception as e:
                import traceback
                LAST_ERROR = traceback.format_exc()
                logger.error("Ошибка polling: %s, повтор через 5 секунд...", e)
                await asyncio.sleep(5)
    except Exception as e:
        import traceback
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
                        logger.info("Keep-Alive ping %s: %s", target_url, resp.status)
                except Exception as e:
                    logger.debug("Keep-Alive error %s: %s", target_url, e)
            await asyncio.sleep(300)  # раз в 5 минут

async def async_main():
    port = int(os.getenv("PORT", "10000"))
    
    # 1. Мгновенно поднимаем Health-Check сервер для Render
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/debug", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health-check веб-сервер запущен на 0.0.0.0:%s", port)

    # 2. Фоновый Keep-Alive пинг
    asyncio.create_task(ping_loop())

    # 3. Загрузка конфигурации
    config = load_config()

    # 4. Запуск бота
    if config.bot_mode == "webhook":
        bot, dp, db = create_bot_and_dispatcher(config)
        run_webhook_mode(bot, dp, config)
    else:
        await run_bot_polling(config)

def main():
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
    except Exception as e:
        logger.exception("Фатальная ошибка: %s", e)

if __name__ == "__main__":
    main()
