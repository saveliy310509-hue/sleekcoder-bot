import html
import logging
from aiogram import Router, Bot, types, F
from aiogram.filters import CommandStart, CommandObject
from bot.config import ADMIN_ID
from bot.database import db
from bot.keyboards.inline import user_admin_shortcut_kb
from bot.ui import (
    show_or_edit,
    safe_delete_user_message,
    safe_delete_message,
    get_last_message_id,
    clear_last_message_id,
    strip_custom_emojis
)

logger = logging.getLogger("user_handlers")
router = Router()

def safe_truncate_caption(text: str, max_len: int = 1024) -> str:
    """Безопасное усечение подписи до допустимого лимита Telegram (1024 символа)"""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."

async def send_file_by_type(bot: Bot, chat_id: int, file_id: str, file_type: str, caption: str):
    """Вспомогательная функция отправки файла нужного типа с поддержкой премиум эмодзи и авто-фоллбэком"""
    send_methods = {
        "document": bot.send_document,
        "video": bot.send_video,
        "audio": bot.send_audio,
        "photo": bot.send_photo,
        "voice": bot.send_voice,
        "animation": bot.send_animation
    }
    
    method = send_methods.get(file_type, bot.send_document)
    kwargs = {"chat_id": chat_id, file_type if file_type in send_methods else "document": file_id}
    caption_truncated = safe_truncate_caption(caption, 1024)
    
    # 1. Попытка отправки с премиум эмодзи в HTML
    try:
        await method(**kwargs, caption=caption_truncated, parse_mode="HTML")
        return True
    except Exception:
        pass
        
    # 2. Если не удалось, пробуем без тегов <tg-emoji>
    try:
        clean_caption = safe_truncate_caption(strip_custom_emojis(caption), 1024)
        await method(**kwargs, caption=clean_caption, parse_mode="HTML")
        return True
    except Exception:
        pass

    # 3. Крайний фоллбэк: как документ без HTML
    try:
        raw_caption = safe_truncate_caption(strip_custom_emojis(caption), 1024)
        await bot.send_document(chat_id=chat_id, document=file_id, caption=raw_caption)
        return True
    except Exception:
        return False

async def deliver_file_by_link(message: types.Message, raw_code: str, bot: Bot) -> bool:
    """Выдача файла по коду или ссылке с подробной обработкой всех краевых случаев"""
    clean_code = (raw_code or "").strip()
    if not clean_code:
        return False

    link = await db.get_link_by_code(clean_code)
    if not link:
        return False

    clicks = await db.increment_link_clicks(link["code"])
    
    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start={link['code']}"
    
    raw_caption = link["caption"] if link.get("caption") else await db.get_text(
        "file_caption_default",
        "📦 <b>{name}</b>\n📥 Скачиваний: <b>{downloads}</b>\n\nВаш файл готов к скачиванию!"
    )
    
    caption = (
        raw_caption
        .replace("{name}", html.escape(link["name"]))
        .replace("{downloads}", str(clicks))
        .replace("{clicks}", str(clicks))
        .replace("{count}", str(clicks))
        .replace("{скачивания}", str(clicks))
        .replace("{скачиваний}", str(clicks))
        .replace("{url}", deep_link)
        .replace("{link}", deep_link)
    )
    
    sent = await send_file_by_type(
        bot=bot,
        chat_id=message.chat.id,
        file_id=link["file_id"],
        file_type=link["file_type"],
        caption=caption
    )
    
    if not sent:
        await show_or_edit(
            bot=bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text=(
                "⚠️ <b>Не удалось отправить файл.</b>\n"
                "Возможно, он был временно недоступен в серверах Telegram. "
                "Попробуйте ещё раз через несколько секунд или обратитесь к администратору."
            )
        )
    return True

@router.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    await safe_delete_user_message(message)
    await db.add_or_update_user(user_id, username, first_name)
    
    code = (command.args or "").strip()
    
    # 1. Если переход был по ссылке (deep link)
    if code:
        # Удаляем предыдущее информационное сообщение бота, чтобы в чате остался только выданный файл
        prev_msg_id = get_last_message_id(user_id)
        if prev_msg_id:
            await safe_delete_message(bot, message.chat.id, prev_msg_id)
            clear_last_message_id(user_id)

        delivered = await deliver_file_by_link(message, code, bot)
        if not delivered:
            not_found_msg = await db.get_text("link_not_found", "❌ Ссылка не найдена или устарела.")
            await show_or_edit(
                bot=bot,
                chat_id=message.chat.id,
                user_id=user_id,
                text=not_found_msg
            )
        return

    # 2. Если обычный /start без параметров
    welcome_default = await db.get_text(
        "welcome_default",
        "👋 <b>Добро пожаловать!</b>\n\nЭтот бот предназначен для скачивания плагинов и файлов по специальным ссылкам."
    )
    reply_kb = user_admin_shortcut_kb() if user_id == ADMIN_ID else None
    await show_or_edit(
        bot=bot,
        chat_id=message.chat.id,
        user_id=user_id,
        text=welcome_default,
        reply_markup=reply_kb
    )

# 3. Обработчик текста: если пользователь отправил ссылку или код в чат текстом
@router.message(F.text)
async def text_link_catcher(message: types.Message, bot: Bot):
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    await safe_delete_user_message(message)

    potential_code = text
    if "start=" in potential_code:
        potential_code = potential_code.split("start=")[-1].split("&")[0].strip()
    elif "t.me/" in potential_code:
        potential_code = potential_code.split("/")[-1].strip()

    prev_msg_id = get_last_message_id(message.from_user.id)
    if prev_msg_id:
        await safe_delete_message(bot, message.chat.id, prev_msg_id)
        clear_last_message_id(message.from_user.id)

    delivered = await deliver_file_by_link(message, potential_code, bot)
    if not delivered:
        not_found_msg = await db.get_text("link_not_found", "❌ Ссылка не найдена или устарела.")
        await show_or_edit(
            bot=bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text=not_found_msg
        )
