import html
import logging
import re
from typing import Optional
from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

logger = logging.getLogger("ui_manager")

# In-memory registry of the active bot message for each user: {user_id: message_id}
_user_last_messages: dict[int, int] = {}

def strip_custom_emojis(html_str: str) -> str:
    """Заменяет <tg-emoji emoji-id="...">EMOJI</tg-emoji> на обычный символ эмодзи"""
    if not html_str:
        return ""
    return re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', html_str)

def get_last_message_id(user_id: int) -> Optional[int]:
    return _user_last_messages.get(user_id)

def set_last_message_id(user_id: int, message_id: int):
    _user_last_messages[user_id] = message_id

def clear_last_message_id(user_id: int):
    _user_last_messages.pop(user_id, None)

async def safe_delete_message(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def safe_delete_user_message(message: types.Message):
    """Удаление входящего сообщения пользователя для сохранения идеальной чистоты чата"""
    try:
        await message.delete()
    except Exception:
        pass

async def _edit_with_fallbacks(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML"
) -> bool:
    """Попытка отредактировать сообщение с многоуровневым фоллбэком при ошибках разметки"""
    # Попытка 1: исходный текст и parse_mode
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True
        if "can't parse entities" not in err and "unsupported" not in err:
            return False

    # Попытка 2: удаление кастомных эмодзи
    try:
        clean = strip_custom_emojis(text)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=clean,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return True
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True
        if "can't parse entities" not in err and "unsupported" not in err:
            return False

    # Попытка 3: чистый текст без форматирования
    try:
        clean = strip_custom_emojis(text)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=clean,
            reply_markup=reply_markup,
            parse_mode=None
        )
        return True
    except Exception:
        return False

async def _send_with_fallbacks(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML"
) -> Optional[types.Message]:
    """Отправка нового сообщения с многоуровневым фоллбэком при ошибках разметки"""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "can't parse entities" not in err and "unsupported" not in err:
            raise

    try:
        clean = strip_custom_emojis(text)
        return await bot.send_message(
            chat_id=chat_id,
            text=clean,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception:
        clean = strip_custom_emojis(text)
        return await bot.send_message(
            chat_id=chat_id,
            text=clean,
            reply_markup=reply_markup,
            parse_mode=None
        )

async def show_or_edit(
    bot: Bot,
    chat_id: int,
    user_id: int,
    text: str,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = "HTML",
    state: Optional[FSMContext] = None,
    force_new: bool = False
) -> Optional[types.Message]:
    """
    Основная функция 'One-Message UI':
    Всегда обновляет ОДНО И ТО ЖЕ сообщение бота в диалоге.
    Если сообщение не существует, было удалено или не может быть отредактировано,
    старое удаляется и отправляется новое, сохраняя его ID для последующих обновлений.
    """
    last_msg_id = _user_last_messages.get(user_id)
    if not last_msg_id and state:
        try:
            data = await state.get_data()
            last_msg_id = data.get("ui_msg_id")
        except Exception:
            pass

    if last_msg_id and not force_new:
        success = await _edit_with_fallbacks(
            bot=bot,
            chat_id=chat_id,
            message_id=last_msg_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        if success:
            set_last_message_id(user_id, last_msg_id)
            if state:
                try:
                    await state.update_data(ui_msg_id=last_msg_id)
                except Exception:
                    pass
            return None

        # Редактирование не удалось (сообщение удалено или устарело)
        await safe_delete_message(bot, chat_id, last_msg_id)

    if force_new and last_msg_id:
        await safe_delete_message(bot, chat_id, last_msg_id)

    # Отправляем новое сообщение и регистрируем его
    new_msg = await _send_with_fallbacks(
        bot=bot,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )
    if new_msg:
        set_last_message_id(user_id, new_msg.message_id)
        if state:
            try:
                await state.update_data(ui_msg_id=new_msg.message_id)
            except Exception:
                pass
    return new_msg
