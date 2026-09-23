import re
from typing import Optional
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def get_start_kb(
    button_text: str = "✍️ Оставить отзыв",
    icon_custom_emoji_id: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Главная инлайн-клавиатура приветствия с настраиваемым текстом кнопки и премиум эмодзи."""
    if icon_custom_emoji_id:
        button_text = re.sub(r"^[^\w\s]+", "", button_text or "").strip()

    button_kwargs = {
        "text": button_text or ("Оставить отзыв" if icon_custom_emoji_id else "✍️ Оставить отзыв"),
        "callback_data": "start_review",
    }
    if icon_custom_emoji_id:
        button_kwargs["icon_custom_emoji_id"] = str(icon_custom_emoji_id)

    buttons = [[InlineKeyboardButton(**button_kwargs)]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_rating_kb() -> ReplyKeyboardMarkup:
    """Клавиатура снизу экрана для выбора оценки от 1 до 5 звезд."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="⭐ 1"),
                KeyboardButton(text="⭐⭐ 2"),
                KeyboardButton(text="⭐⭐⭐ 3"),
            ],
            [
                KeyboardButton(text="⭐⭐⭐⭐ 4"),
                KeyboardButton(text="⭐⭐⭐⭐⭐ 5"),
            ],
            [
                KeyboardButton(text="❌ Отмена"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выберите оценку от 1 до 5 звёзд...",
    )


def get_cancel_reply_kb() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены внизу экрана."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    """Удаление обычной клавиатуры."""
    return ReplyKeyboardRemove()
