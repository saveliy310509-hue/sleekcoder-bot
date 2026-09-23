import html
import logging
import traceback
from typing import Optional

from aiogram import Bot, Router
from aiogram.types import ErrorEvent
from config import Config, load_config

logger = logging.getLogger("SleekCodeBot.Errors")
errors_router = Router(name="errors_router")

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None


@errors_router.error()
async def global_error_handler(
    event: ErrorEvent,
    bot: Optional[Bot] = None,
    config: Optional[Config] = None,
):
    """
    Глобальный обработчик ошибок:
    1. Логирует ошибку в консоль/лог-файл.
    2. Отправляет ошибку в Sentry / GlitchTip (если настроен).
    3. Отправляет подробный алерт с трейсбеком администраторам в чат Telegram.
    4. Отправляет пользователю понятное и вежливое уведомление, предотвращая зависание UI.
    """
    exception = event.exception
    update = event.update

    logger.error(
        "Необработанное исключение: %s: %s",
        type(exception).__name__,
        exception,
        exc_info=True,
    )

    # 1. Отправка в Sentry / GlitchTip при наличии
    if sentry_sdk:
        try:
            sentry_sdk.capture_exception(exception)
        except Exception as sentry_err:
            logger.warning("Не удалось отправить исключение в Sentry: %s", sentry_err)

    if bot is None:
        bot = Bot.get_current()

    if config is None:
        try:
            config = load_config()
        except Exception:
            config = None

    # 2. Сбор контекста ошибки
    user_info = "Неизвестно"
    action_info = "Неизвестно"
    chat_id: Optional[int] = None

    if update:
        if update.message:
            chat_id = update.message.chat.id
            u = update.message.from_user
            if u:
                username_str = f"@{u.username}" if u.username else "нет username"
                user_info = f"<b>{html.escape(u.full_name)}</b> ({username_str}, ID: <code>{u.id}</code>)"
            text_preview = update.message.text or update.message.caption or "[Медиа/Файл]"
            action_info = f"Сообщение: <i>{html.escape(text_preview[:120])}</i>"

        elif update.callback_query:
            chat_id = update.callback_query.message.chat.id if update.callback_query.message else None
            u = update.callback_query.from_user
            if u:
                username_str = f"@{u.username}" if u.username else "нет username"
                user_info = f"<b>{html.escape(u.full_name)}</b> ({username_str}, ID: <code>{u.id}</code>)"
            cb_data = update.callback_query.data or "[Нет данных]"
            action_info = f"Кнопка (callback_data): <code>{html.escape(cb_data)}</code>"

        else:
            event_type = getattr(update, "event_type", "update")
            action_info = f"Событие типа: <code>{html.escape(str(event_type))}</code>"

    # Формируем трейсбек (обрезаем до 2500 символов под лимиты Telegram)
    tb_lines = traceback.format_exception(type(exception), exception, exception.__traceback__)
    tb_text = "".join(tb_lines)
    if len(tb_text) > 2500:
        tb_text = "..." + tb_text[-2500:]

    escaped_tb = html.escape(tb_text)
    error_type = html.escape(type(exception).__name__)
    error_msg = html.escape(str(exception) or "Без описания")

    admin_alert = (
        f"🚨 <b>Внимание! Ошибка в работе бота!</b>\n\n"
        f"<b>Тип ошибки:</b> <code>{error_type}</code>\n"
        f"<b>Описание:</b> <code>{error_msg}</code>\n\n"
        f"👤 <b>Пользователь:</b> {user_info}\n"
        f"🎯 <b>Действие:</b> {action_info}\n\n"
        f"📋 <b>Traceback:</b>\n"
        f"<pre><code class=\"language-python\">{escaped_tb}</code></pre>"
    )

    # 3. Отправляем алерт всем администраторам
    if bot and config and config.admin_ids:
        for admin_id in config.admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_alert,
                    parse_mode="HTML",
                )
            except Exception as alert_err:
                logger.error("Не удалось отправить алерт админу %s: %s", admin_id, alert_err)

    # 4. Вежливый ответ пользователю, чтобы Telegram UI не зависал
    if update:
        try:
            if update.callback_query:
                await update.callback_query.answer(
                    "⚠️ Произошла ошибка. Администраторы уже оповещены!",
                    show_alert=True,
                )
            elif update.message and chat_id and bot:
                admin_ids = config.admin_ids if config else []
                if chat_id not in admin_ids:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ <b>Произошла ошибка при обработке запроса.</b>\n"
                             "Администраторы уже получили отчет и устраняют проблему. Попробуйте чуть позже!",
                        parse_mode="HTML",
                    )
        except Exception:
            pass

    return True
