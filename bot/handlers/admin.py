import html
import math
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import ADMIN_ID
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
    links_list_kb,
    link_detail_kb,
    link_delete_confirm_kb,
    texts_list_kb,
    text_view_kb,
    cancel_kb
)
from bot.handlers.create import extract_file_data
from bot.handlers.user import strip_custom_emojis

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# --- Главное меню админки ---

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "⚙️ <b>Панель управления администратора</b>\n\n"
        "Выберите нужный раздел из меню ниже:",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("У вас нет прав доступа.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Панель управления администратора</b>\n\n"
        "Выберите нужный раздел из меню ниже:",
        reply_markup=admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text("🔒 Панель администратора закрыта. Чтобы открыть снова, введите /admin")
    await callback.answer()

# --- Статистика ---

@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    stats = await db.get_stats()
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"🔗 Всего активных ссылок: <b>{stats['total_links']}</b>\n"
        f"📥 Всего скачиваний файлов: <b>{stats['total_downloads']}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Запуск создания ссылки из меню ---

@router.callback_query(F.data == "admin:create")
async def cb_admin_create(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(CreateLinkState.waiting_for_name)
    await callback.message.edit_text(
        "➕ <b>Создание новой ссылки</b>\n\n"
        "Введите название для новой ссылки (например, название плагина или архива):\n\n"
        "<i>Или отправьте команду вида <code>/create Название</code></i>",
        reply_markup=cancel_kb("admin:menu"),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Список ссылок с пагинацией ---

@router.callback_query(F.data.startswith("admin:links:"))
async def cb_admin_links_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
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
        await callback.message.edit_text(
            "📋 <b>Список ссылок пуст.</b>\n\n"
            "Вы еще не создали ни одной ссылки. Создайте первую с помощью кнопки ниже или командой <code>/create &lt;название&gt;</code>.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin:create")],
                [types.InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return
        
    await callback.message.edit_text(
        f"📋 <b>Список ссылок</b> (Всего: {total_links}):\n\n"
        "Выберите ссылку для подробной информации и управления:",
        reply_markup=links_list_kb(links, page, total_pages),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Просмотр конкретной ссылки ---

@router.callback_query(F.data.startswith("admin:link:"))
async def cb_admin_link_view(callback: types.CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        return
        
    parts = callback.data.split(":")
    link_id = int(parts[2])
    
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена или была удалена.", show_alert=True)
        await cb_admin_links_list(callback)
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
    
    text = (
        f"📁 <b>Информация о ссылке #{link['id']}</b>\n\n"
        f"🏷 <b>Название:</b> {html.escape(link['name'])}\n"
        f"📦 <b>Тип файла:</b> {type_names.get(link['file_type'], link['file_type'])}\n"
        f"📥 <b>Скачиваний:</b> {link['clicks']}\n"
        f"📝 <b>Индивидуальная подпись:</b> {caption_preview}\n"
        f"📅 <b>Дата создания:</b> {link['created_at']}\n\n"
        f"🔗 <b>Прямая ссылка:</b>\n<code>{url}</code>"
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=link_detail_kb(link_id, bot_info.username, link["code"]),
            parse_mode="HTML"
        )
    except Exception:
        clean_caption = strip_custom_emojis(link["caption"]) if link.get("caption") else "<i>Стандартная (из настроек)</i>"
        fallback_text = (
            f"📁 <b>Информация о ссылке #{link['id']}</b>\n\n"
            f"🏷 <b>Название:</b> {html.escape(link['name'])}\n"
            f"📦 <b>Тип файла:</b> {type_names.get(link['file_type'], link['file_type'])}\n"
            f"📥 <b>Скачиваний:</b> {link['clicks']}\n"
            f"📝 <b>Индивидуальная подпись:</b> {clean_caption}\n"
            f"📅 <b>Дата создания:</b> {link['created_at']}\n\n"
            f"🔗 <b>Прямая ссылка:</b>\n<code>{url}</code>"
        )
        await callback.message.edit_text(
            fallback_text,
            reply_markup=link_detail_kb(link_id, bot_info.username, link["code"]),
            parse_mode="HTML"
        )
    await callback.answer()

# --- Удаление ссылки ---

@router.callback_query(F.data.startswith("admin:link_delete:"))
async def cb_admin_link_delete(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите удалить ссылку <b>{html.escape(link['name'])}</b>?\n\n"
        f"После удаления пользователи не смогут скачивать данный файл по этой ссылке.",
        reply_markup=link_delete_confirm_kb(link_id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin:link_delete_confirm:"))
async def cb_admin_link_delete_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    link_id = int(callback.data.split(":")[2])
    success = await db.delete_link(link_id)
    if success:
        await callback.answer("✅ Ссылка успешно удалена!", show_alert=True)
    else:
        await callback.answer("Ссылка не найдена.", show_alert=True)
    
    # Возвращаемся к списку
    total_links = await db.count_links()
    links = await db.get_links_paginated(limit=5, offset=0)
    total_pages = max(1, math.ceil(total_links / 5))
    if not links:
        await callback.message.edit_text(
            "📋 <b>Список ссылок пуст.</b>",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin:create")],
                [types.InlineKeyboardButton(text="🔙 В меню", callback_data="admin:menu")]
            ]),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Список ссылок</b> (Всего: {total_links}):",
            reply_markup=links_list_kb(links, 1, total_pages),
            parse_mode="HTML"
        )

# --- Замена файла ссылки ---

@router.callback_query(F.data.startswith("admin:link_edit_file:"))
async def cb_admin_link_edit_file(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
        
    await state.update_data(link_id=link_id)
    await state.set_state(ChangeFileState.waiting_for_new_file)
    await callback.message.edit_text(
        f"🔄 <b>Замена файла для ссылки: {html.escape(link['name'])}</b>\n\n"
        "Отправьте новый файл (документ, архив, видео, аудио или фото), который заменит текущий:",
        reply_markup=cancel_kb(f"admin:link:{link_id}"),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ChangeFileState.waiting_for_new_file)
async def process_new_file(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    file_id, file_unique_id, file_type = extract_file_data(message)
    if not file_id:
        await message.answer("⚠️ Пожалуйста, отправьте файл (документ, архив, видео, фото и т.д.):")
        return
    data = await state.get_data()
    link_id = data.get("link_id")
    await db.update_link_file(link_id, file_id, file_unique_id, file_type)
    await state.clear()
    
    bot_info = await bot.get_me()
    link = await db.get_link_by_id(link_id)
    await message.answer(
        f"✅ <b>Файл для ссылки успешно обновлен!</b>\n\n"
        f"Ссылка осталась прежней, теперь пользователи будут получать обновленный файл.",
        reply_markup=link_detail_kb(link_id, bot_info.username, link["code"]),
        parse_mode="HTML"
    )

# --- Редактирование названия ссылки ---

@router.callback_query(F.data.startswith("admin:link_edit_name:"))
async def cb_admin_link_edit_name(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
        
    await state.update_data(link_id=link_id)
    await state.set_state(ChangeNameState.waiting_for_new_name)
    await callback.message.edit_text(
        f"✏️ <b>Изменение названия</b>\n\n"
        f"Текущее название: <b>{html.escape(link['name'])}</b>\n\n"
        "Отправьте новое название:",
        reply_markup=cancel_kb(f"admin:link:{link_id}"),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ChangeNameState.waiting_for_new_name)
async def process_new_name(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("⚠️ Введите текстовое название:")
        return
    data = await state.get_data()
    link_id = data.get("link_id")
    await db.update_link_name(link_id, new_name)
    await state.clear()
    
    bot_info = await bot.get_me()
    link = await db.get_link_by_id(link_id)
    await message.answer(
        f"✅ <b>Название ссылки изменено на:</b> {html.escape(new_name)}",
        reply_markup=link_detail_kb(link_id, bot_info.username, link["code"]),
        parse_mode="HTML"
    )

# --- Редактирование индивидуального описания ссылки ---

@router.callback_query(F.data.startswith("admin:link_edit_caption:"))
async def cb_admin_link_edit_caption(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    link_id = int(callback.data.split(":")[2])
    link = await db.get_link_by_id(link_id)
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
        
    await state.update_data(link_id=link_id)
    await state.set_state(ChangeCaptionState.waiting_for_new_caption)
    cur_cap = html.escape(link["caption"]) if link.get("caption") else "<i>Не установлено (используется стандартное)</i>"
    await callback.message.edit_text(
        f"📝 <b>Редактирование подписи к файлу</b>\n\n"
        f"Текущая подпись: {cur_cap}\n\n"
        "Отправьте новый текст подписи (поддерживается HTML-разметка, премиум эмодзи, теги <code>{name}</code> и <code>{downloads}</code>).\n"
        "Если хотите сбросить подпись на стандартную, отправьте <code>-</code> (дефис):",
        reply_markup=cancel_kb(f"admin:link:{link_id}"),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(ChangeCaptionState.waiting_for_new_caption)
async def process_new_caption(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
        
    raw_text = (message.text or message.caption or "").strip()
    new_caption = (message.html_text if message.html_text else raw_text).strip()
    data = await state.get_data()
    link_id = data.get("link_id")
    
    if raw_text == "-":
        await db.update_link_caption(link_id, None)
        msg_result = "✅ Индивидуальная подпись удалена. Теперь будет использоваться стандартная!"
    else:
        await db.update_link_caption(link_id, new_caption)
        msg_result = "✅ Индивидуальная подпись для ссылки успешно сохранена!"
        
    await state.clear()
    bot_info = await bot.get_me()
    link = await db.get_link_by_id(link_id)
    try:
        await message.answer(
            msg_result,
            reply_markup=link_detail_kb(link_id, bot_info.username, link["code"]),
            parse_mode="HTML"
        )
    except Exception:
        await message.answer(
            msg_result,
            reply_markup=link_detail_kb(link_id, bot_info.username, link["code"])
        )

# --- Редактирование всех системных сообщений бота ---

@router.callback_query(F.data == "admin:texts")
async def cb_admin_texts(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    texts = await db.get_all_texts()
    await callback.message.edit_text(
        "✏️ <b>Редактирование текстов и сообщений бота</b>\n\n"
        "Выберите сообщение, которое хотите изменить:",
        reply_markup=texts_list_kb(texts),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin:text_view:"))
async def cb_admin_text_view(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":", 2)[2]
    item = await db.get_text_item(key)
    if not item:
        await callback.answer("Текст не найден.", show_alert=True)
        return
        
    text = (
        f"💬 <b>{html.escape(item['title'])}</b>\n"
        f"Ключ: <code>{key}</code>\n\n"
        f"<b>Предпросмотр:</b>\n"
        f"<blockquote>{item['value']}</blockquote>\n\n"
        f"<i>Поддерживается HTML разметка и премиум эмодзи. "
        f"Для подписи файла доступны теги: <code>{{name}}</code> (название) и <code>{{downloads}}</code> (кол-во скачиваний).</i>"
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=text_view_kb(key),
            parse_mode="HTML"
        )
    except Exception:
        fallback_text = (
            f"💬 <b>{html.escape(item['title'])}</b>\n"
            f"Ключ: <code>{key}</code>\n\n"
            f"<b>Предпросмотр:</b>\n"
            f"<blockquote>{strip_custom_emojis(item['value'])}</blockquote>\n\n"
            f"<i>Поддерживается HTML разметка и премиум эмодзи. "
            f"Для подписи файла доступны теги: <code>{{name}}</code> (название) и <code>{{downloads}}</code> (кол-во скачиваний).</i>"
        )
        await callback.message.edit_text(
            fallback_text,
            reply_markup=text_view_kb(key),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("admin:text_edit:"))
async def cb_admin_text_edit(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":", 2)[2]
    item = await db.get_text_item(key)
    if not item:
        await callback.answer("Текст не найден.", show_alert=True)
        return
        
    await state.update_data(edit_text_key=key)
    await state.set_state(EditTextState.waiting_for_new_text)
    
    await callback.message.edit_text(
        f"✏️ <b>Редактирование: {html.escape(item['title'])}</b>\n\n"
        f"Отправьте новый текст сообщением (можно с премиум эмодзи и форматированием).\n\n"
        f"<i>Текущий текст для удобного копирования/редактирования:</i>\n"
        f"<code>{html.escape(item['value'])}</code>",
        reply_markup=cancel_kb(f"admin:text_view:{key}"),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EditTextState.waiting_for_new_text)
async def process_new_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    new_text = message.html_text if message.html_text else message.text
    if not new_text:
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение:")
        return
        
    data = await state.get_data()
    key = data.get("edit_text_key")
    await db.update_text(key, new_text)
    await state.clear()
    
    item = await db.get_text_item(key)
    try:
        await message.answer(
            f"✅ <b>Текст «{html.escape(item['title'])}» успешно обновлен!</b>\n\n"
            f"<b>Новый текст:</b>\n"
            f"<blockquote>{new_text}</blockquote>",
            reply_markup=text_view_kb(key),
            parse_mode="HTML"
        )
    except Exception:
        await message.answer(
            f"✅ <b>Текст «{html.escape(item['title'])}» успешно обновлен!</b>\n\n"
            f"<b>Новый текст:</b>\n"
            f"<blockquote>{strip_custom_emojis(new_text)}</blockquote>",
            reply_markup=text_view_kb(key),
            parse_mode="HTML"
        )

# Кнопка-заглушка для номера страницы
@router.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()
