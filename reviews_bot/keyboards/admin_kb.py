from typing import List, Optional
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню панели администратора."""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="📝 Отзывы", callback_data="admin:reviews:0:all"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast"),
            InlineKeyboardButton(text="🚫 Чёрный список", callback_data="admin:blacklist"),
        ],
        [
            InlineKeyboardButton(text="💬 Все сообщения", callback_data="admin:messages_menu"),
            InlineKeyboardButton(text="🔘 Все кнопки", callback_data="admin:buttons_menu"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Канал отзывов", callback_data="admin:channel_settings"),
            InlineKeyboardButton(text="📥 Экспорт в CSV", callback_data="admin:export"),
        ],
        [
            InlineKeyboardButton(text="🔄 Закрыть панель", callback_data="admin:close"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_buttons_menu_kb() -> InlineKeyboardMarkup:
    """Меню выбора кнопки для редактирования."""
    keyboard = [
        [
            InlineKeyboardButton(text="✍️ Кнопка «Оставить отзыв»", callback_data="admin:btn:start_review"),
        ],
        [
            InlineKeyboardButton(text="⭐ Оценка 1", callback_data="admin:btn:rate_1"),
            InlineKeyboardButton(text="⭐⭐ Оценка 2", callback_data="admin:btn:rate_2"),
        ],
        [
            InlineKeyboardButton(text="⭐⭐⭐ Оценка 3", callback_data="admin:btn:rate_3"),
            InlineKeyboardButton(text="⭐⭐⭐⭐ Оценка 4", callback_data="admin:btn:rate_4"),
        ],
        [
            InlineKeyboardButton(text="⭐⭐⭐⭐⭐ Оценка 5", callback_data="admin:btn:rate_5"),
            InlineKeyboardButton(text="❌ Кнопка «Отмена»", callback_data="admin:btn:cancel"),
        ],
        [
            InlineKeyboardButton(text="💬 «Ответить»", callback_data="admin:btn:card_reply"),
            InlineKeyboardButton(text="📢 «В канал»", callback_data="admin:btn:card_publish"),
        ],
        [
            InlineKeyboardButton(text="🚫 «Забанить»", callback_data="admin:btn:card_ban"),
            InlineKeyboardButton(text="🗑️ «Удалить»", callback_data="admin:btn:card_delete"),
        ],
        [
            InlineKeyboardButton(text="⭐️ Премиум-звезда (для отзывов)", callback_data="admin:btn:star_icon"),
        ],
        [
            InlineKeyboardButton(text="🔄 Сбросить ВСЕ кнопки", callback_data="admin:btn_reset_all"),
        ],
        [
            InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_button_item_kb(key: str) -> InlineKeyboardMarkup:
    """Клавиатура для конкретной кнопки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Изменить кнопку", callback_data=f"admin:btn_edit:{key}"),
                InlineKeyboardButton(text="🔄 Сбросить", callback_data=f"admin:btn_reset:{key}"),
            ],
            [
                InlineKeyboardButton(text="🔙 К списку кнопок", callback_data="admin:buttons_menu"),
            ],
        ]
    )


def get_messages_menu_kb() -> InlineKeyboardMarkup:
    """Меню выбора сообщения для редактирования."""
    keyboard = [
        [
            InlineKeyboardButton(text="👋 Приветствие (/start)", callback_data="admin:msg:welcome"),
        ],
        [
            InlineKeyboardButton(text="✍️ Запрос текста отзыва", callback_data="admin:msg:review_prompt"),
        ],
        [
            InlineKeyboardButton(text="🌟 Запрос оценки (1-5)", callback_data="admin:msg:rating_prompt"),
        ],
        [
            InlineKeyboardButton(text="✅ Успешный отзыв", callback_data="admin:msg:review_success"),
        ],
        [
            InlineKeyboardButton(text="📬 Отзыв для админа", callback_data="admin:msg:admin_new_review"),
        ],
        [
            InlineKeyboardButton(text="❌ Сообщение отмены", callback_data="admin:msg:cancel"),
            InlineKeyboardButton(text="⛔️ Сообщение бана", callback_data="admin:msg:banned"),
        ],
        [
            InlineKeyboardButton(text="🔘 Кнопка «Оставить отзыв»", callback_data="admin:edit_button"),
        ],
        [
            InlineKeyboardButton(text="🔄 Сбросить ВСЕ сообщения", callback_data="admin:msg_reset_all"),
        ],
        [
            InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_message_item_kb(key: str) -> InlineKeyboardMarkup:
    """Клавиатура для конкретного сообщения."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"admin:msg_edit:{key}"),
                InlineKeyboardButton(text="🔄 Сбросить текст", callback_data=f"admin:msg_reset:{key}"),
            ],
            [
                InlineKeyboardButton(text="🔙 К списку сообщений", callback_data="admin:messages_menu"),
            ],
        ]
    )


def get_welcome_settings_kb() -> InlineKeyboardMarkup:
    """Клавиатура управления приветственным сообщением и кнопкой отзыва."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Текст сообщения", callback_data="admin:edit_welcome"),
                InlineKeyboardButton(text="🔘 Текст кнопки", callback_data="admin:edit_button"),
            ],
            [
                InlineKeyboardButton(text="🔄 Сбросить по умолчанию", callback_data="admin:reset_welcome"),
            ],
            [
                InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu"),
            ],
        ]
    )


def get_review_card_actions_kb(
    review_id: int,
    user_id: int,
    is_published: bool = False,
) -> InlineKeyboardMarkup:
    """Кнопки действий под новым отзывом, пришедшим админу."""
    pub_text = "✅ Опубликовано" if is_published else "📢 В канал"
    pub_data = "admin:noop" if is_published else f"admin:publish:{review_id}"

    keyboard = [
        [
            InlineKeyboardButton(text="💬 Ответить", callback_data=f"admin:reply:{review_id}"),
            InlineKeyboardButton(text=pub_text, callback_data=pub_data),
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin:ban_user:{user_id}"),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin:del_review:{review_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_reviews_list_kb(
    review_id: int,
    user_id: int,
    current_index: int,
    total_count: int,
    rating_filter: str = "all",
    is_published: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура для листания отзывов в админке."""
    pub_text = "✅ В канале" if is_published else "📢 В канал"
    pub_data = "admin:noop" if is_published else f"admin:publish_list:{review_id}:{current_index}:{rating_filter}"

    # Кнопки действий над этим отзывом
    action_row = [
        InlineKeyboardButton(text="💬 Ответить", callback_data=f"admin:reply:{review_id}"),
        InlineKeyboardButton(text=pub_text, callback_data=pub_data),
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin:del_list:{review_id}:{current_index}:{rating_filter}"),
    ]

    # Навигация влево / вправо
    nav_row = []
    if current_index > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"admin:reviews:{current_index - 1}:{rating_filter}",
            )
        )
    nav_row.append(
        InlineKeyboardButton(
            text=f"{current_index + 1} / {total_count}",
            callback_data="admin:noop",
        )
    )
    if current_index + 1 < total_count:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"admin:reviews:{current_index + 1}:{rating_filter}",
            )
        )

    # Фильтр по оценкам
    filter_row = [
        InlineKeyboardButton(
            text="⭐️ Все" if rating_filter == "all" else "Все",
            callback_data=f"admin:reviews:0:all",
        ),
        InlineKeyboardButton(
            text="⭐️ 5" if rating_filter == "5" else "5★",
            callback_data=f"admin:reviews:0:5",
        ),
        InlineKeyboardButton(
            text="⭐️ 4" if rating_filter == "4" else "4★",
            callback_data=f"admin:reviews:0:4",
        ),
        InlineKeyboardButton(
            text="⭐️ 1-3" if rating_filter == "low" else "1-3★",
            callback_data=f"admin:reviews:0:low",
        ),
    ]

    keyboard = [
        action_row,
        nav_row,
        filter_row,
        [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_broadcast_confirm_kb() -> InlineKeyboardMarkup:
    """Подтверждение рассылки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Начать отправку", callback_data="admin:broadcast_start"),
                InlineKeyboardButton(text="❌ Отменить", callback_data="admin:broadcast_cancel"),
            ]
        ]
    )


def get_blacklist_menu_kb(banned_count: int = 0) -> InlineKeyboardMarkup:
    """Меню черного списка."""
    buttons = [
        [InlineKeyboardButton(text="➕ Заблокировать по ID", callback_data="admin:ban_by_id")],
    ]
    if banned_count > 0:
        buttons.append([InlineKeyboardButton(text="📋 Список заблокированных", callback_data="admin:banned_list")])
        buttons.append([InlineKeyboardButton(text="🔓 Разблокировать по ID", callback_data="admin:unban_by_id")])

    buttons.append([InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_admin_kb() -> InlineKeyboardMarkup:
    """Кнопка возврата в админ-меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu")]
        ]
    )


def get_cancel_state_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены текущего FSM действия админа."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel_action")]
        ]
    )
