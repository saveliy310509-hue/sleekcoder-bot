import re
from typing import Any, Dict, Optional
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from database.db import Database

DEFAULT_BUTTONS: Dict[str, Dict[str, Any]] = {
    "start_review": {
        "title": "✍️ Кнопка «Оставить отзыв»",
        "desc": "Главная кнопка в приветственном сообщении (/start)",
        "default": "✍️ Оставить отзыв",
        "supports_premium": True,
    },
    "rate_1": {
        "title": "⭐ Оценка 1",
        "desc": "Кнопка для оценки 1 звезда (поддерживает Premium эмодзи)",
        "default": "⭐ 1",
        "supports_premium": True,
    },
    "rate_2": {
        "title": "⭐⭐ Оценка 2",
        "desc": "Кнопка для оценки 2 звезды (поддерживает Premium эмодзи)",
        "default": "⭐⭐ 2",
        "supports_premium": True,
    },
    "rate_3": {
        "title": "⭐⭐⭐ Оценка 3",
        "desc": "Кнопка для оценки 3 звезды (поддерживает Premium эмодзи)",
        "default": "⭐⭐⭐ 3",
        "supports_premium": True,
    },
    "rate_4": {
        "title": "⭐⭐⭐⭐ Оценка 4",
        "desc": "Кнопка для оценки 4 звезды (поддерживает Premium эмодзи)",
        "default": "⭐⭐⭐⭐ 4",
        "supports_premium": True,
    },
    "rate_5": {
        "title": "⭐⭐⭐⭐⭐ Оценка 5",
        "desc": "Кнопка для оценки 5 звёзд (поддерживает Premium эмодзи)",
        "default": "⭐⭐⭐⭐⭐ 5",
        "supports_premium": True,
    },
    "cancel": {
        "title": "❌ Кнопка «Отмена»",
        "desc": "Кнопка для отмены процесса отзыва (поддерживает Premium эмодзи)",
        "default": "❌ Отмена",
        "supports_premium": True,
    },
    "card_reply": {
        "title": "💬 Кнопка «Ответить»",
        "desc": "Инлайн-кнопка под новым отзывом для ответа клиенту",
        "default": "💬 Ответить",
        "supports_premium": True,
    },
    "card_publish": {
        "title": "📢 Кнопка «В канал»",
        "desc": "Инлайн-кнопка под отзывом для публикации в канал",
        "default": "📢 В канал",
        "supports_premium": True,
    },
    "card_ban": {
        "title": "🚫 Кнопка «Забанить»",
        "desc": "Инлайн-кнопка под отзывом для блокировки автора",
        "default": "🚫 Забанить",
        "supports_premium": True,
    },
    "card_delete": {
        "title": "🗑️ Кнопка «Удалить»",
        "desc": "Инлайн-кнопка под отзывом для удаления отзыва",
        "default": "🗑️ Удалить",
        "supports_premium": True,
    },
    "star_icon": {
        "title": "⭐️ Премиум-эмодзи звезды (для отзывов)",
        "desc": "Иконка звезды в карточке отзыва у админа и в канале",
        "default": "⭐",
        "supports_premium": True,
    },
}


async def get_button_text(db: Database, key: str) -> str:
    """Получение актуального текста кнопки."""
    custom = await db.get_setting(f"btn_text_{key}")
    if custom and custom.strip():
        return custom

    # Обратная совместимость для кнопки старта
    if key == "start_review":
        old_btn = await db.get_setting("button_review_text")
        if old_btn and old_btn.strip():
            return old_btn

    return DEFAULT_BUTTONS.get(key, {}).get("default", "")


async def get_button_emoji_id(db: Database, key: str) -> Optional[str]:
    """Получение ID премиум-эмодзи для кнопки (если есть)."""
    custom = await db.get_setting(f"btn_emoji_{key}")
    if custom and custom.strip():
        return custom

    if key == "start_review":
        old_emoji = await db.get_setting("button_review_emoji_id")
        if old_emoji and old_emoji.strip():
            return old_emoji

    return None


async def set_custom_button(
    db: Database,
    key: str,
    text: str,
    emoji_id: Optional[str] = None,
):
    """Сохранение кастомного текста и премиум-эмодзи кнопки."""
    await db.set_setting(f"btn_text_{key}", text)
    await db.set_setting(f"btn_emoji_{key}", emoji_id or "")

    if key == "start_review":
        await db.set_setting("button_review_text", text)
        await db.set_setting("button_review_emoji_id", emoji_id or "")


async def reset_custom_button(db: Database, key: str):
    """Сброс конкретной кнопки на стандартную."""
    await db.set_setting(f"btn_text_{key}", "")
    await db.set_setting(f"btn_emoji_{key}", "")

    if key == "start_review":
        await db.set_setting("button_review_text", "")
        await db.set_setting("button_review_emoji_id", "")


async def reset_all_buttons(db: Database):
    """Сброс абсолютно всех кнопок по умолчанию."""
    for key in DEFAULT_BUTTONS.keys():
        await reset_custom_button(db, key)


async def build_start_kb(db: Database) -> InlineKeyboardMarkup:
    """Формирование главной инлайн-клавиатуры /start с кастомным текстом и премиум-эмодзи."""
    text = await get_button_text(db, "start_review")
    emoji_id = await get_button_emoji_id(db, "start_review")

    if emoji_id:
        text = re.sub(r"^[^\w\s]+", "", text).strip() or text

    kwargs = {
        "text": text or ("Оставить отзыв" if emoji_id else "✍️ Оставить отзыв"),
        "callback_data": "start_review",
    }
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = emoji_id

    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(**kwargs)]])


async def build_rating_kb(db: Database) -> InlineKeyboardMarkup:
    """Формирование инлайн-клавиатуры выбора звёзд (1-5) с поддержкой кастомных текстов и премиум-эмодзи."""
    async def make_rate_btn(r: int):
        text = await get_button_text(db, f"rate_{r}")
        emoji_id = await get_button_emoji_id(db, f"rate_{r}")
        if emoji_id:
            text = re.sub(r"^[^\w\s]+", "", text).strip() or text
        kw = {
            "text": text or str(r),
            "callback_data": f"rate:{r}",
        }
        if emoji_id:
            kw["icon_custom_emoji_id"] = emoji_id
        return InlineKeyboardButton(**kw)

    b1 = await make_rate_btn(1)
    b2 = await make_rate_btn(2)
    b3 = await make_rate_btn(3)
    b4 = await make_rate_btn(4)
    b5 = await make_rate_btn(5)

    c_text = await get_button_text(db, "cancel")
    c_emoji = await get_button_emoji_id(db, "cancel")
    if c_emoji:
        c_text = re.sub(r"^[^\w\s]+", "", c_text).strip() or c_text
    c_kw = {
        "text": c_text or "❌ Отмена",
        "callback_data": "user_cancel",
    }
    if c_emoji:
        c_kw["icon_custom_emoji_id"] = c_emoji
    c_btn = InlineKeyboardButton(**c_kw)

    # Если тексты короткие, красиво отображаем в 1 строку 1-5, иначе 3 + 2
    if all(len(b.text or "") <= 4 for b in [b1, b2, b3, b4, b5]):
        rate_rows = [[b1, b2, b3, b4, b5]]
    else:
        rate_rows = [[b1, b2, b3], [b4, b5]]

    rate_rows.append([c_btn])
    return InlineKeyboardMarkup(inline_keyboard=rate_rows)


async def build_cancel_kb(db: Database) -> InlineKeyboardMarkup:
    """Формирование инлайн-кнопки отмены с кастомным текстом и премиум-эмодзи."""
    c_text = await get_button_text(db, "cancel")
    c_emoji = await get_button_emoji_id(db, "cancel")
    if c_emoji:
        c_text = re.sub(r"^[^\w\s]+", "", c_text).strip() or c_text
    c_kw = {
        "text": c_text or "❌ Отмена",
        "callback_data": "user_cancel",
    }
    if c_emoji:
        c_kw["icon_custom_emoji_id"] = c_emoji
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(**c_kw)]])


async def build_review_card_actions_kb(
    db: Database,
    review_id: int,
    user_id: int,
    is_published: bool = False,
) -> InlineKeyboardMarkup:
    """Формирование кнопок действий под новым отзывом с кастомными текстами."""
    reply_text = await get_button_text(db, "card_reply")
    reply_emoji = await get_button_emoji_id(db, "card_reply")

    pub_text = "✅ Опубликовано" if is_published else await get_button_text(db, "card_publish")
    pub_emoji = None if is_published else await get_button_emoji_id(db, "card_publish")
    pub_data = "admin:noop" if is_published else f"admin:publish:{review_id}"

    ban_text = await get_button_text(db, "card_ban")
    ban_emoji = await get_button_emoji_id(db, "card_ban")

    del_text = await get_button_text(db, "card_delete")
    del_emoji = await get_button_emoji_id(db, "card_delete")

    def make_btn(text, cb, emoji=None):
        if emoji:
            text = re.sub(r"^[^\w\s]+", "", text).strip() or text
        kw = {"text": text, "callback_data": cb}
        if emoji:
            kw["icon_custom_emoji_id"] = emoji
        return InlineKeyboardButton(**kw)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [make_btn(reply_text, f"admin:reply:{review_id}", reply_emoji), make_btn(pub_text, pub_data, pub_emoji)],
            [make_btn(ban_text, f"admin:ban_user:{user_id}", ban_emoji), make_btn(del_text, f"admin:del_review:{review_id}", del_emoji)],
        ]
    )
