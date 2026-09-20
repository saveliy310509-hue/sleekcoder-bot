import html
from aiogram import Router, Bot, types
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
    
    # 1. Попытка отправки с премиум эмодзи в HTML
    try:
        await method(**kwargs, caption=caption, parse_mode="HTML")
        return True
    except Exception:
        pass
        
    # 2. Если не удалось (например, Telegram отклонил премиум эмодзи), пробуем со снятием тегов <tg-emoji>
    try:
        clean_caption = strip_custom_emojis(caption)
        await method(**kwargs, caption=clean_caption, parse_mode="HTML")
        return True
    except Exception:
        pass

    # 3. Крайний фоллбэк: как документ без HTML
    try:
        await bot.send_document(chat_id=chat_id, document=file_id, caption=strip_custom_emojis(caption)[:1024])
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

@router.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Сохраняем/обновляем пользователя в базе данных
    await db.add_or_update_user(user_id, username, first_name)
    
    code = command.args
    
    # 1. Если переход был по ссылке (deep link)
    if code:
        link = await db.get_link_by_code(code)
        if not link:
            not_found_msg = await db.get_text("link_not_found", "❌ Ссылка не найдена или устарела.")
            await safe_answer(message, not_found_msg)
            return
        
        # Увеличиваем счетчик скачиваний и получаем актуальное значение
        clicks = await db.increment_link_clicks(code)
        
        # Получаем имя бота для формирования ссылки при необходимости
        bot_info = await bot.get_me()
        deep_link = f"https://t.me/{bot_info.username}?start={code}"
        
        # Формируем подпись к файлу (персональная или стандартная)
        raw_caption = link["caption"] if link.get("caption") else await db.get_text(
            "file_caption_default",
            "📦 <b>{name}</b>\n📥 Скачиваний: <b>{downloads}</b>\n\nВаш файл готов к скачиванию!"
        )
        
        # Подстановка плейсхолдеров
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
                "⚠️ Не удалось отправить файл. Возможно, он был удалён с серверов Telegram."
            )
        return

    # 2. Если обычный /start без параметров (для всех пользователей и админа при тестировании)
    welcome_default = await db.get_text(
        "welcome_default",
        "👋 <b>Добро пожаловать!</b>\n\nЭтот бот предназначен для скачивания плагинов и файлов по специальным ссылкам."
    )
    await safe_answer(message, welcome_default)

