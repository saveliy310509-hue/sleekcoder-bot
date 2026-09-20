from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any

def admin_main_kb() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin:create")],
        [InlineKeyboardButton(text="📋 Список ссылок", callback_data="admin:links:1")],
        [InlineKeyboardButton(text="✏️ Редактировать сообщения", callback_data="admin:texts")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin:close")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def user_admin_shortcut_kb() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚙️ Панель администратора", callback_data="admin:menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def links_list_kb(links: List[Dict[str, Any]], current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    keyboard = []
    
    for link in links:
        keyboard.append([
            InlineKeyboardButton(
                text=f"📁 {link['name']} ({link['clicks']} 📥)",
                callback_data=f"admin:link:{link['id']}"
            )
        ])
    
    # Навигационные кнопки
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:links:{current_page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin:links:{current_page + 1}"))
    
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([
        InlineKeyboardButton(text="➕ Создать новую", callback_data="admin:create"),
        InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def link_detail_kb(link_id: int, bot_username: str, code: str) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/{bot_username}?start={code}"
    keyboard = [
        [
            InlineKeyboardButton(text="🔗 Скопировать/Перейти", url=share_url)
        ],
        [
            InlineKeyboardButton(text="🔄 Заменить файл", callback_data=f"admin:link_edit_file:{link_id}"),
            InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"admin:link_edit_caption:{link_id}")
        ],
        [
            InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"admin:link_edit_name:{link_id}"),
            InlineKeyboardButton(text="🗑️ Удалить ссылку", callback_data=f"admin:link_delete:{link_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 К списку ссылок", callback_data="admin:links:1")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def link_delete_confirm_kb(link_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🗑️ Да, удалить навсегда", callback_data=f"admin:link_delete_confirm:{link_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin:link:{link_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def texts_list_kb(texts: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    keyboard = []
    for t in texts:
        keyboard.append([
            InlineKeyboardButton(text=f"💬 {t['title']}", callback_data=f"admin:text_view:{t['key']}")
        ])
    keyboard.append([
        InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def text_view_kb(key: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data=f"admin:text_edit:{key}")],
        [InlineKeyboardButton(text="🔙 К списку сообщений", callback_data="admin:texts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def cancel_kb(back_callback: str = "admin:menu") -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def created_link_kb(bot_username: str, code: str, link_id: int) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/{bot_username}?start={code}"
    keyboard = [
        [InlineKeyboardButton(text="🔗 Проверить ссылку", url=share_url)],
        [InlineKeyboardButton(text="⚙️ Управление ссылкой", callback_data=f"admin:link:{link_id}")],
        [InlineKeyboardButton(text="➕ Создать ещё одну", callback_data="admin:create")],
        [InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin:menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
