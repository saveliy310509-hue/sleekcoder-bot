import html
from aiogram import Router, Bot, types, F
from aiogram.filters import CommandStart, CommandObject
from bot.config import ADMIN_ID
from bot.database import db

router = Router()

import re

def strip_custom_emojis(html_str: str) -> str:
    """Заменяет <tg-emoji emoji-id="...">EMOJI</tg-emoji> на обычный символ эмодзи"""
    if not html_str:
        return ""
    return re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', html_str)

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
        
    # 2. Если не удалось (например, Telegram отклонил премиум эмодзи), пробуем со снятием тегов <tg-emoji>
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

async def safe_answer(message: types.Message, text: str):
    """Безопасная отправка ответа с премиум эмодзи и фоллбэком при ошибке парсинга"""
    try:
        await message.answer(text, parse_mode="HTML")
    except Exception:
        try:
            await message.answer(strip_custom_emojis(text), parse_mode="HTML")
        except Exception:
            await message.answer(strip_custom_emojis(text))

async def deliver_file_by_link(message: types.Message, raw_code: str, bot: Bot) -> bool:
    """Выдача файла по коду или ссылке с подробной обработкой всех краевых случаев"""
    clean_code = (raw_code or "").strip()
    if not clean_code:
        return False

    link = await db.get_link_by_code(clean_code)
    if not link:
        return False

    # Увеличиваем счетчик скачиваний
    clicks = await db.increment_link_clicks(link["code"])
    
    # Получаем имя бота для формирования ссылки
    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start={link['code']}"
    
    # Формируем подпись к файлу
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
    
    # Отправляем файл пользователю
    sent = await send_file_by_type(
        bot=bot,
        chat_id=message.chat.id,
        file_id=link["file_id"],
        file_type=link["file_type"],
        caption=caption
    )
    
    if not sent:
        await safe_answer(
            message,
            "⚠️ Не удалось отправить файл. Возможно, он был временно недоступен в серверах Telegram. "
            "Попробуйте ещё раз через несколько секунд или обратитесь к администратору."
        )
    return True

@router.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Сохраняем/обновляем пользователя в базе данных
    await db.add_or_update_user(user_id, username, first_name)
    
    code = (command.args or "").strip()
    
    # 1. Если переход был по ссылке (deep link)
    if code:
        delivered = await deliver_file_by_link(message, code, bot)
        if not delivered:
            not_found_msg = await db.get_text("link_not_found", "❌ Ссылка не найдена или устарела.")
            await safe_answer(message, not_found_msg)
        return

    # 2. Если обычный /start без параметров
    welcome_default = await db.get_text(
        "welcome_default",
        "👋 <b>Добро пожаловать!</b>\n\nЭтот бот предназначен для скачивания плагинов и файлов по специальным ссылкам."
    )
    await safe_answer(message, welcome_default)

# 3. Дополнительный хэндлер: если пользователь просто отправил ссылку или код в чат текстом
@router.message(F.text)
async def text_link_catcher(message: types.Message, bot: Bot):
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    # Проверяем, содержит ли текст код ссылки или URL
    potential_code = text
    if "start=" in potential_code:
        potential_code = potential_code.split("start=")[-1].split("&")[0].strip()
    elif "t.me/" in potential_code:
        potential_code = potential_code.split("/")[-1].strip()

    delivered = await deliver_file_by_link(message, potential_code, bot)
    if not delivered:
        # Если это просто сообщение и не ссылка — ничего не отвечаем или даем приветствие
        pass

