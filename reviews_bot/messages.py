from typing import Any, Dict, Optional
from database.db import Database

DEFAULT_MESSAGES: Dict[str, Dict[str, Any]] = {
    "welcome": {
        "title": "👋 Приветствие (/start)",
        "desc": "Приветственное сообщение при вводе команды /start",
        "placeholders": ["{name}"],
        "default": (
            "👋 <b>Здравствуйте, {name}!</b>\n\n"
            "Добро пожаловать в официального бота отзывов <b>SleekCode</b>.\n\n"
            "Здесь вы можете оставить свой честный отзыв о нашей работе. "
            "Вы можете написать любой текст, использовать форматирование и даже "
            "<b>премиум эмодзи</b> — мы бережно всё сохраним!\n\n"
            "Для того чтобы оставить отзыв, нажмите кнопку ниже или отправьте команду /review."
        ),
    },
    "review_prompt": {
        "title": "✍️ Запрос текста отзыва",
        "desc": "Сообщение с просьбой написать отзыв",
        "placeholders": [],
        "default": (
            "✍️ <b>Напишите ваш отзыв:</b>\n\n"
            "Поделитесь вашими впечатлениями, замечаниями или пожеланиями. "
            "Поддерживается форматирование и премиум эмодзи.\n\n"
            "<i>Для отмены нажмите кнопку «❌ Отмена» внизу экрана.</i>"
        ),
    },
    "rating_prompt": {
        "title": "🌟 Запрос оценки (1-5)",
        "desc": "Сообщение после отправки текста с просьбой выбрать оценку",
        "placeholders": [],
        "default": (
            "🌟 <b>Спасибо за текст отзыва!</b>\n\n"
            "Теперь, пожалуйста, оцените нашу работу от <b>1</b> до <b>5</b> звёзд:\n"
            "<i>Выберите вариант на клавиатуре внизу 👇</i>"
        ),
    },
    "review_success": {
        "title": "✅ Успешная отправка",
        "desc": "Благодарность после выбора оценки",
        "placeholders": ["{stars}", "{rating}"],
        "default": (
            "✅ <b>Спасибо за ваш отзыв!</b>\n\n"
            "Ваша оценка: {stars} ({rating}/5)\n"
            "Ваш отзыв успешно передан нашей команде. Мы постоянно совершенствуемся благодаря вам! ❤️"
        ),
    },
    "cancel": {
        "title": "❌ Отмена действия",
        "desc": "Сообщение при отмене процесса отзыва",
        "placeholders": [],
        "default": (
            "❌ <b>Отправка отзыва отменена.</b>\n"
            "Вы всегда можете начать заново с помощью команды /start."
        ),
    },
    "banned": {
        "title": "⛔️ Сообщение бана",
        "desc": "Сообщение, если заблокированный пользователь пишет в бота",
        "placeholders": [],
        "default": (
            "⛔️ <b>Доступ ограничен.</b>\n"
            "Вы были заблокированы администратором и не можете отправлять отзывы."
        ),
    },
    "admin_new_review": {
        "title": "📬 Уведомление админу о новом отзыве",
        "desc": "Карточка нового отзыва, отправляемая администраторам в ЛС",
        "placeholders": ["{text}", "{stars}", "{rating}", "{author}", "{user_id}", "{name}"],
        "default": (
            "<b>Новый отзыв!</b>\n\n"
            "{text}\n"
            "{stars}\n\n"
            "{author}"
        ),
    },
}


async def get_message_template(db: Database, key: str) -> str:
    """Возвращает сырой шаблон сообщения из БД или стандартный."""
    custom = await db.get_setting(f"msg_{key}")
    if custom and custom.strip():
        return custom
    # Для обратной совместимости с ранее сохраненным welcome_text
    if key == "welcome":
        old_welcome = await db.get_setting("welcome_text")
        if old_welcome and old_welcome.strip():
            return old_welcome

    return DEFAULT_MESSAGES.get(key, {}).get("default", "")


async def render_message(db: Database, key: str, **kwargs) -> str:
    """Возвращает сообщение с подставленными плейсхолдерами."""
    text = await get_message_template(db, key)
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


async def set_custom_message(db: Database, key: str, text: str):
    """Сохранение кастомного текста сообщения."""
    await db.set_setting(f"msg_{key}", text)
    if key == "welcome":
        await db.set_setting("welcome_text", text)


async def reset_custom_message(db: Database, key: str):
    """Сброс сообщения на стандартное."""
    await db.set_setting(f"msg_{key}", "")
    if key == "welcome":
        await db.set_setting("welcome_text", "")


async def reset_all_messages(db: Database):
    """Сброс абсолютно всех сообщений и кнопки на стандартные."""
    for key in DEFAULT_MESSAGES.keys():
        await reset_custom_message(db, key)
    await db.set_setting("button_review_text", "")
    await db.set_setting("button_review_emoji_id", "")
