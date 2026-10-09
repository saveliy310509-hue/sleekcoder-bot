import html
import math
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import ADMIN_ID, DB_PATH
from bot.database import db
from bot.states.admin_states import (
    CreateLinkState,
    EditTextState,
    ChangeFileState,
    ChangeCaptionState,
    ChangeNameState
)
from bot.keyboards.inline import (
    admin_main_kb,
    admin_backup_kb,
    links_list_kb,
    link_detail_kb,
    link_delete_confirm_kb,
    texts_list_kb,
    text_view_kb,
    cancel_kb
)
from bot.handlers.create import extract_file_data
from bot.storage_sync import sync_on_startup, trigger_backup_save, LOCAL_BACKUP_FILE
from bot.ui import (
    show_or_edit,
    safe_delete_user_message,
    set_last_message_id,
    strip_custom_emojis
)

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# --- Вспомогательные функции рендеринга экранов ---

async def render_link_view(bot: Bot, chat_id: int, user_id: int, link_id: int, notice: str = ""):
    link = await db.get_link_by_id(link_id)
    if not link:
        await show_or_edit(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            text="⚠️ <b>Ссылка не найдена или была удалена.</b>",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 К списку ссылок", callback_data="admin:links:1")]
            ])
        )
        return

    bot_info = await bot.get_me()
    url = f"https://t.me/{bot_info.username}?start={link['code']}"

    type_names = {
        "document": "📁 Документ/Архив",
        "video": "🎬 Видео",
        "audio": "🎵 Аудио",
        "photo": "🖼️ Фотография",
        "voice": "🎤 Голос",
        "animation": "🎞️ GIF"
    }

    caption_preview = link["caption"] if link.get("caption") else "<i>Стандартная (из настроек)</i>"
    notice_text = f"{notice}\n\n" if notice else ""

    text = (
        f"{notice_text}"
        f"📁 <b>Информация о ссылке #{link['id']}</b>\n\n"
        f"🏷 <b>Название:</b> {html.escape(link['name'])}\n"
        f"📦 <b>Тип файла:</b> {type_names.get(link['file_type'], link['file_type'])}\n"
        f"📥 <b>Скачиваний:</b> {link['clicks']}\n"
        f"📝 <b>Индивидуальная подпись:</b> {caption_preview}\n"
        f"📅 <b>Дата создания:</b> {link['created_at']}\n\n"
        f"🔗 <b>Прямая ссылка:</b>\n<code>{url}</code>"
    )

    await show_or_edit(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        reply_markup=link_detail_kb(link_id, bot_info.username, link["code"])
    )


async def render_text_view(bot: Bot, chat_id: int, user_id: int, key: str, notice: str = ""):
    item = await db.get_text_item(key)
    if not item:
        await show_or_edit(
            bot=bot,
            chat_id=chat_id,
            user_id=user_id,
            text="⚠️ Текст не найден.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="🔙 К списку сообщений", callback_data="admin:texts")]
            ])
        )
        return

    notice_text = f"{notice}\n\n" if notice else ""
    text = (
        f"{notice_text}"
        f"💬 <b>{html.escape(item['title'])}</b>\n"
        f"Ключ: <code>{key}</code>\n\n"
        f"<b>Предпросмотр:</b>\n"
        f"<blockquote>{item['value']}</blockquote>\n\n"
        f"<i>Поддерживается HTML разметка и премиум эмодзи. "
        f"Для подписи файла доступны теги: <code>{{name}}</code> (название) и <code>{{downloads}}</code> (кол-во скачиваний).</i>"
    )

    await show_or_edit(
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        reply_markup=text_view_kb(key)
    )


# --- Главное меню админки ---

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await safe_delete_user_message(message)
    await state.clear()
    await show_or_edit(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        text=(
            "⚙️ <b>Панель управления администратора</b>\n\n"
            "Выберите нужный раздел из меню ниже:"
        ),
        reply_markup=admin_main_kb()
    )

@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав доступа.", show_alert=True)
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    await state.clear()
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            "⚙️ <b>Панель управления администратора</b>\n\n"
            "Выберите нужный раздел из меню ниже:"
        ),
        reply_markup=admin_main_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    await state.clear()
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            "🔒 <b>Панель администратора закрыта.</b>\n\n"
            "Чтобы открыть панель снова, отправьте команду /admin"
        ),
        reply_markup=None
    )
    await callback.answer()

# --- Статистика ---

@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    stats = await db.get_stats()
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"🔗 Всего активных ссылок: <b>{stats['total_links']}</b>\n"
        f"📥 Всего скачиваний файлов: <b>{stats['total_downloads']}</b>"
    )
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")]
        ])
    )
    await callback.answer()

# --- Запуск создания ссылки из меню ---

@router.callback_query(F.data == "admin:create")
async def cb_admin_create(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    await state.set_state(CreateLinkState.waiting_for_name)
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            "➕ <b>Создание новой ссылки</b>\n\n"
            "Введите название для новой ссылки (например, название плагина или архива):\n\n"
            "<i>Или отправьте команду вида <code>/create Название</code></i>"
        ),
        reply_markup=cancel_kb("admin:menu"),
        state=state
    )
    await callback.answer()

# --- Список ссылок с пагинацией ---

@router.callback_query(F.data.startswith("admin:links:"))
async def cb_admin_links_list(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    
    parts = callback.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    per_page = 5
    
    total_links = await db.count_links()
    total_pages = max(1, math.ceil(total_links / per_page))
    if page > total_pages:
        page = total_pages
        
    offset = (page - 1) * per_page
    links = await db.get_links_paginated(limit=per_page, offset=offset)
    
    if not links:
        await show_or_edit(
            bot=bot,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            text=(
                "📋 <b>Список ссылок пуст.</b>\n\n"
                "Вы еще не создали ни одной ссылки. Создайте первую с помощью кнопки ниже."
            ),
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin:create")],
                [types.InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")]
            ])
        )
        await callback.answer()
        return
        
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"📋 <b>Список ссылок</b> (Всего: {total_links}):\n\n"
            "Выберите ссылку для подробной информации и управления:"
        ),
        reply_markup=links_list_kb(links, page, total_pages)
    )
    await callback.answer()

# --- Просмотр конкретной ссылки ---

@router.callback_query(F.data.startswith("admin:link:"))
async def cb_admin_link_view(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    parts = callback.data.split(":")
    link_id = int(parts[2])
    await render_link_view(bot, callback.message.chat.id, callback.from_user.id, link_id)
    await callback.answer()

# --- Удаление ссылки ---

@router.callback_query(F.data.startswith("admin:link_delete:"))
async def cb_admin_link_delete(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"⚠️ <b>Подтверждение удаления</b>\n\n"
            f"Вы действительно хотите удалить ссылку <b>{html.escape(link['name'])}</b>?\n\n"
            f"После удаления пользователи не смогут скачивать данный файл по этой ссылке."
        ),
        reply_markup=link_delete_confirm_kb(link_id)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin:link_delete_confirm:"))
async def cb_admin_link_delete_confirm(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    link_id = int(callback.data.split(":")[2])
    success = await db.delete_link(link_id)
    if success:
        await callback.answer("✅ Ссылка успешно удалена!", show_alert=True)
    else:
        await callback.answer("Ссылка не найдена.", show_alert=True)
    
    total_links = await db.count_links()
    links = await db.get_links_paginated(limit=5, offset=0)
    total_pages = max(1, math.ceil(total_links / 5))
    if not links:
        await show_or_edit(
            bot=bot,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            text="📋 <b>Список ссылок пуст.</b>",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin:create")],
                [types.InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")]
            ])
        )
    else:
        await show_or_edit(
            bot=bot,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            text=f"📋 <b>Список ссылок</b> (Всего: {total_links}):",
            reply_markup=links_list_kb(links, 1, total_pages)
        )

# --- Замена файла ссылки ---

@router.callback_query(F.data.startswith("admin:link_edit_file:"))
async def cb_admin_link_edit_file(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
        
    await state.update_data(link_id=link_id)
    await state.set_state(ChangeFileState.waiting_for_new_file)
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"🔄 <b>Замена файла для ссылки: {html.escape(link['name'])}</b>\n\n"
            "Отправьте новый файл (документ, архив, видео, аудио или фото), который заменит текущий:"
        ),
        reply_markup=cancel_kb(f"admin:link:{link_id}"),
        state=state
    )
    await callback.answer()

@router.message(ChangeFileState.waiting_for_new_file)
async def process_new_file(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    file_id, file_unique_id, file_type = extract_file_data(message)
    await safe_delete_user_message(message)
    data = await state.get_data()
    link_id = data.get("link_id")
    
    if not file_id:
        await show_or_edit(
            bot=bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text="⚠️ <b>Пожалуйста, отправьте именно файл</b> (документ, архив, видео, фото и т.д.):",
            reply_markup=cancel_kb(f"admin:link:{link_id}"),
            state=state
        )
        return
        
    await db.update_link_file(link_id, file_id, file_unique_id, file_type)
    await state.clear()
    await render_link_view(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        link_id=link_id,
        notice="✅ <b>Файл для ссылки успешно обновлен!</b>"
    )

# --- Редактирование названия ссылки ---

@router.callback_query(F.data.startswith("admin:link_edit_name:"))
async def cb_admin_link_edit_name(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
        
    await state.update_data(link_id=link_id)
    await state.set_state(ChangeNameState.waiting_for_new_name)
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"✏️ <b>Изменение названия</b>\n\n"
            f"Текущее название: <b>{html.escape(link['name'])}</b>\n\n"
            "Отправьте новое название:"
        ),
        reply_markup=cancel_kb(f"admin:link:{link_id}"),
        state=state
    )
    await callback.answer()

@router.message(ChangeNameState.waiting_for_new_name)
async def process_new_name(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    new_name = (message.text or "").strip()
    await safe_delete_user_message(message)
    data = await state.get_data()
    link_id = data.get("link_id")
    
    if not new_name:
        await show_or_edit(
            bot=bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text="⚠️ <b>Пожалуйста, введите текстовое название:</b>",
            reply_markup=cancel_kb(f"admin:link:{link_id}"),
            state=state
        )
        return
        
    await db.update_link_name(link_id, new_name)
    await state.clear()
    await render_link_view(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        link_id=link_id,
        notice=f"✅ <b>Название ссылки изменено на:</b> {html.escape(new_name)}"
    )

# --- Редактирование индивидуального описания ссылки ---

@router.callback_query(F.data.startswith("admin:link_edit_caption:"))
async def cb_admin_link_edit_caption(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
        
    await state.update_data(link_id=link_id)
    await state.set_state(ChangeCaptionState.waiting_for_new_caption)
    cur_cap = html.escape(link["caption"]) if link.get("caption") else "<i>Не установлено (используется стандартное)</i>"
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"📝 <b>Редактирование подписи к файлу</b>\n\n"
            f"Текущая подпись: {cur_cap}\n\n"
            "Отправьте новый текст подписи (поддерживается HTML-разметка, премиум эмодзи, теги <code>{name}</code> и <code>{downloads}</code>).\n"
            "Если хотите сбросить подпись на стандартную, отправьте <code>-</code> (дефис):"
        ),
        reply_markup=cancel_kb(f"admin:link:{link_id}"),
        state=state
    )
    await callback.answer()

@router.message(ChangeCaptionState.waiting_for_new_caption)
async def process_new_caption(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
        
    raw_text = (message.text or message.caption or "").strip()
    new_caption = (message.html_text if message.html_text else raw_text).strip()
    await safe_delete_user_message(message)
    data = await state.get_data()
    link_id = data.get("link_id")
    
    if raw_text == "-":
        await db.update_link_caption(link_id, None)
        notice_text = "✅ <b>Индивидуальная подпись сброшена на стандартную!</b>"
    else:
        await db.update_link_caption(link_id, new_caption)
        notice_text = "✅ <b>Индивидуальная подпись для ссылки успешно сохранена!</b>"
        
    await state.clear()
    await render_link_view(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        link_id=link_id,
        notice=notice_text
    )

# --- Редактирование всех системных сообщений бота ---

@router.callback_query(F.data == "admin:texts")
async def cb_admin_texts(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    texts = await db.get_all_texts()
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            "✏️ <b>Редактирование текстов и сообщений бота</b>\n\n"
            "Выберите сообщение, которое хотите изменить:"
        ),
        reply_markup=texts_list_kb(texts)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin:text_view:"))
async def cb_admin_text_view(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    key = callback.data.split(":", 2)[2]
    await render_text_view(bot, callback.message.chat.id, callback.from_user.id, key)
    await callback.answer()

@router.callback_query(F.data.startswith("admin:text_edit:"))
async def cb_admin_text_edit(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    key = callback.data.split(":", 2)[2]
    item = await db.get_text_item(key)
    if not item:
        await callback.answer("Текст не найден.", show_alert=True)
        return
        
    await state.update_data(edit_text_key=key)
    await state.set_state(EditTextState.waiting_for_new_text)
    
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"✏️ <b>Редактирование: {html.escape(item['title'])}</b>\n\n"
            f"Отправьте новый текст сообщением (можно с премиум эмодзи и форматированием).\n\n"
            f"<i>Текущий текст для удобного копирования/редактирования:</i>\n"
            f"<code>{html.escape(item['value'])}</code>"
        ),
        reply_markup=cancel_kb(f"admin:text_view:{key}"),
        state=state
    )
    await callback.answer()

@router.message(EditTextState.waiting_for_new_text)
async def process_new_text(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    new_text = message.html_text if message.html_text else message.text
    await safe_delete_user_message(message)
    data = await state.get_data()
    key = data.get("edit_text_key")
    
    if not new_text:
        await show_or_edit(
            bot=bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            text="⚠️ <b>Пожалуйста, отправьте текстовое сообщение:</b>",
            reply_markup=cancel_kb(f"admin:text_view:{key}"),
            state=state
        )
        return
        
    await db.update_text(key, new_text)
    await state.clear()
    await render_text_view(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        key=key,
        notice="✅ <b>Текст успешно сохранен и обновлен!</b>"
    )

# Кнопка-заглушка для номера страницы
@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()

# --- Резервное копирование и облачная синхронизация ---

@router.message(Command("backup"))
async def cmd_backup(message: types.Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await safe_delete_user_message(message)
    trigger_backup_save(DB_PATH)
    links_cnt = await db.count_links()
    
    from aiogram.types import FSInputFile
    if LOCAL_BACKUP_FILE.exists():
        await bot.send_document(
            chat_id=message.chat.id,
            document=FSInputFile(LOCAL_BACKUP_FILE, filename="links_backup.json"),
            caption=f"💾 <b>Резервная копия ссылок (JSON)</b>\nВсего ссылок: <b>{links_cnt}</b>",
            parse_mode="HTML"
        )
    if DB_PATH.exists():
        await bot.send_document(
            chat_id=message.chat.id,
            document=FSInputFile(DB_PATH, filename="bot_data.db"),
            caption="🗄 <b>Файл базы данных SQLite</b>",
            parse_mode="HTML"
        )

@router.message(Command("sync"))
async def cmd_sync(message: types.Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await safe_delete_user_message(message)
    await show_or_edit(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        text="⏳ <b>Синхронизируем базу данных с облачным хранилищем...</b>"
    )
    await sync_on_startup(DB_PATH)
    cnt = await db.count_links()
    await show_or_edit(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        text=f"✅ <b>Синхронизация успешно завершена!</b>\n\nАктивных ссылок в базе данных: <b>{cnt}</b>",
        reply_markup=admin_backup_kb()
    )

@router.callback_query(F.data == "admin:backup_menu")
async def cb_admin_backup_menu(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    cnt = await db.count_links()
    cloud_status = "Подключено (GitHub Sync)"
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"💾 <b>Резервное копирование и облачная синхронизация</b>\n\n"
            f"📊 Активных ссылок в базе: <b>{cnt}</b>\n"
            f"☁️ Облачное хранилище: <b>{cloud_status}</b>\n\n"
            f"Все созданные ссылки автоматически сохраняются в защищенное облако. "
            f"Даже если хостинг перезагрузит сервер, все ссылки мгновенно восстанавливаются автоматически."
        ),
        reply_markup=admin_backup_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "admin:sync_now")
async def cb_admin_sync_now(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    await callback.answer("⏳ Синхронизация с облаком...")
    await sync_on_startup(DB_PATH)
    cnt = await db.count_links()
    await show_or_edit(
        bot=bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        text=(
            f"✅ <b>Синхронизация успешно завершена!</b>\n\n"
            f"📊 Актуальное количество ссылок: <b>{cnt}</b>\n\n"
            f"Все ссылки обновлены и готовы к выдаче пользователям."
        ),
        reply_markup=admin_backup_kb()
    )

@router.callback_query(F.data == "admin:backup_download")
async def cb_admin_backup_download(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
    set_last_message_id(callback.from_user.id, callback.message.message_id)
    await callback.answer("Отправка файлов...")
    trigger_backup_save(DB_PATH)
    from aiogram.types import FSInputFile
    cnt = await db.count_links()
    if LOCAL_BACKUP_FILE.exists():
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=FSInputFile(LOCAL_BACKUP_FILE, filename="links_backup.json"),
            caption=f"💾 <b>Резервная копия ссылок (JSON)</b>\nВсего ссылок: <b>{cnt}</b>",
            parse_mode="HTML"
        )
    if DB_PATH.exists():
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=FSInputFile(DB_PATH, filename="bot_data.db"),
            caption="🗄 <b>Файл базы данных SQLite</b>",
            parse_mode="HTML"
        )
