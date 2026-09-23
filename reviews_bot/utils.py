import html
import re
from typing import Optional
from database.db import Database
from messages import render_message


def format_stars(rating: int, star_emoji_id: Optional[str] = None) -> str:
    """Возвращает строку со звёздами эмодзи (от 1 до 5)."""
    rating = max(1, min(5, rating))
    if star_emoji_id and str(star_emoji_id).strip():
        return f'<tg-emoji emoji-id="{star_emoji_id.strip()}">⭐</tg-emoji>' * rating
    return "⭐" * rating


async def get_star_display(db: Database, rating: int) -> str:
    """Возвращает форматированную строку со звёздами (с премиум эмодзи, если задан)."""
    rating = max(1, min(5, rating))

    # 1. Проверяем настройку иконки звезды star_icon
    star_emoji = await db.get_setting("btn_emoji_star_icon")

    # 2. Если не задано явно, проверяем кнопки rate_1..rate_5
    if not star_emoji:
        for r in (1, 5, 2, 3, 4):
            e = await db.get_setting(f"btn_emoji_rate_{r}")
            if e and e.strip():
                star_emoji = e
                break

    if star_emoji and star_emoji.strip():
        return f'<tg-emoji emoji-id="{star_emoji.strip()}">⭐</tg-emoji>' * rating

    star_text = await db.get_setting("btn_text_star_icon")
    if star_text and star_text.strip():
        return star_text.strip() * rating

    return "⭐" * rating


def parse_rating(text: str) -> Optional[int]:
    """Парсит оценку от 1 до 5 из текста сообщения или нажатой кнопки."""
    clean = text.strip()
    # Проверка цифр
    match = re.search(r"\b([1-5])\b", clean)
    if match:
        return int(match.group(1))

    # Подсчет количества звезд эмодзи
    star_count = clean.count("⭐") or clean.count("⭐️")
    if 1 <= star_count <= 5:
        return star_count

    return None


def format_user_tag(user_id: int, username: Optional[str], first_name: Optional[str] = None) -> str:
    """Форматирование юзернейма / ссылки на профиль."""
    if username:
        clean_user = username.lstrip("@")
        return f"@{clean_user}"
    else:
        name = html.escape(first_name or f"Пользователь {user_id}")
        return f'<a href="tg://user?id={user_id}">{name}</a> (ID: {user_id})'


def format_review_message(
    text_html: str,
    rating: int,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str] = None,
    star_emoji_id: Optional[str] = None,
) -> str:
    """Форматирует сообщение отзыва в стандартном формате."""
    stars = format_stars(rating, star_emoji_id)
    user_tag = format_user_tag(user_id, username, first_name)

    return (
        f"<b>Новый отзыв!</b>\n\n"
        f"{text_html}\n"
        f"{stars}\n\n"
        f"{user_tag}"
    )


async def render_admin_review_message(
    db: Database,
    text_html: str,
    rating: int,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str] = None,
) -> str:
    """Рендерит настраиваемое сообщение для администратора о новом отзыве (с поддержкой премиум-звезд)."""
    stars_str = await get_star_display(db, rating)
    user_tag = format_user_tag(user_id, username, first_name)
    author_str = f"@{username.lstrip('@')}" if username else user_tag
    name = first_name or f"Пользователь {user_id}"

    return await render_message(
        db,
        "admin_new_review",
        text=text_html,
        stars=stars_str,
        rating=rating,
        author=author_str,
        user_id=user_id,
        name=name,
    )


def format_channel_post(
    text_html: str,
    rating: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    user_id: Optional[int] = None,
    stars_display: Optional[str] = None,
) -> str:
    """Форматирование отзыва для публикации в публичный канал."""
    stars = stars_display or format_stars(rating)
    author_str = ""
    if username:
        author_str = f"Автор: @{username.lstrip('@')}"
    elif first_name:
        author_str = f"Автор: {html.escape(first_name)}"
    else:
        author_str = "Автор: Клиент"

    return (
        f"⭐️ <b>Отзыв клиента:</b>\n\n"
        f"{text_html}\n\n"
        f"<b>Оценка:</b> {stars}\n"
        f"<i>{author_str}</i>"
    )


def extract_button_info(
    text: str,
    entities: Optional[list] = None,
    fallback_text: str = "",
) -> tuple[str, Optional[str]]:
    """Извлекает текст кнопки и ID кастомного (премиум) эмодзи.
    Если есть премиум эмодзи, убирает обычный подлежащий эмодзи, чтобы не было дублей."""
    icon_custom_emoji_id = None
    cleaned_text = (text or "").strip()

    if entities:
        for entity in entities:
            entity_type = getattr(entity, "type", None)
            emoji_id = getattr(entity, "custom_emoji_id", None)
            if entity_type == "custom_emoji" and emoji_id:
                icon_custom_emoji_id = emoji_id
                try:
                    encoded = text.encode("utf-16-le")
                    start = entity.offset * 2
                    end = (entity.offset + entity.length) * 2
                    res = (encoded[:start] + encoded[end:]).decode("utf-16-le").strip()
                    cleaned_text = res
                except Exception:
                    pass
                break

    if icon_custom_emoji_id:
        # Убираем любые обычные эмодзи перед текстом, чтобы не было двойного значка
        cleaned_text = re.sub(r"^[^\w\s]+", "", cleaned_text).strip()

    if not cleaned_text:
        cleaned_text = fallback_text or (" " if icon_custom_emoji_id else "Оставить отзыв")

    return cleaned_text, icon_custom_emoji_id
