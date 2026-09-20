import html
import secrets
from aiogram import Router, Bot, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext

from bot.config import ADMIN_ID
from bot.database import db
from bot.states.admin_states import CreateLinkState
from bot.keyboards.inline import cancel_kb, created_link_kb

router = Router()

def extract_file_data(message: types.Message):
    """Извлечение file_id, file_unique_id и типа файла из сообщения"""
    if message.document:
        return message.document.file_id, message.document.file_unique_id, "document"
    elif message.video:
        return message.video.file_id, message.video.file_unique_id, "video"
    elif message.audio:
        return message.audio.file_id, message.audio.file_unique_id, "audio"
    elif message.photo:
        # Берем фото наивысшего качества
        best_photo = message.photo[-1]
        return best_photo.file_id, best_photo.file_unique_id, "photo"
    elif message.voice:
        return message.voice.file_id, message.voice.file_unique_id, "voice"
    elif message.animation:
        return message.animation.file_id, message.animation.file_unique_id, "animation"
    return None, None, None

@router.message(Command("create"))
async def cmd_create(message: types.Message, command: CommandObject, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return  # Игнорируем не-админов
        
    await state.clear()
    
    # Если название передано прямо в команде: /create MyPlugin
    if command.args and command.args.strip():
        name = command.args.strip()
        await state.update_data(link_name=name)
        await state.set_state(CreateLinkState.waiting_for_file)
        await message.answer(
            f"📝 Название ссылки: <b>{html.escape(name)}</b>\n\n"
            "📥 Теперь <b>отправьте файл</b> (архив .zip/.rar, документ, видео, аудио или фото), "
            "который бот будет выдавать пользователям по этой ссылке:",
            reply_markup=cancel_kb("admin:menu"),
            parse_mode="HTML"
        )
    else:
        # Если название не указано, запрашиваем его
        await state.set_state(CreateLinkState.waiting_for_name)
        await message.answer(
            "➕ <b>Создание новой ссылки</b>\n\n"
            "Введите название ссылки (например, название плагина, программы или файла):",
            reply_markup=cancel_kb("admin:menu"),
            parse_mode="HTML"
        )

@router.message(CreateLinkState.waiting_for_name)
async def process_link_name(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
        
    name = (message.text or "").strip()
    if not name:
        await message.answer("⚠️ Пожалуйста, введите текстовое название для ссылки:")
        return
        
    await state.update_data(link_name=name)
    await state.set_state(CreateLinkState.waiting_for_file)
    await message.answer(
        f"📝 Название ссылки: <b>{html.escape(name)}</b>\n\n"
        "📥 Теперь <b>отправьте файл</b> (архив .zip/.rar, документ, видео, аудио или фото), "
        "который бот будет выдавать пользователям по этой ссылке:",
        reply_markup=cancel_kb("admin:menu"),
        parse_mode="HTML"
    )

@router.message(CreateLinkState.waiting_for_file)
async def process_link_file(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        return
        
    file_id, file_unique_id, file_type = extract_file_data(message)
    
    if not file_id:
        await message.answer(
            "⚠️ Пожалуйста, отправьте именно файл (документ, архив, видео, аудио или фото):",
            reply_markup=cancel_kb("admin:menu")
        )
        return
        
    data = await state.get_data()
    name = data.get("link_name", "Файл")
    
    # Генерируем уникальный код ссылки (urlsafe, 8 символов)
    while True:
        code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")
        existing = await db.get_link_by_code(code)
        if not existing:
            break
            
    # Сохраняем индивидуальную подпись, если админ прикрепил описание к файлу (с поддержкой премиум эмодзи)
    initial_caption = message.html_text if message.caption else None

    link_id = await db.create_link(
        code=code,
        name=name,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_type=file_type,
        caption=initial_caption
    )
    
    await state.clear()
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    deep_link = f"https://t.me/{bot_username}?start={code}"
    
    type_names = {
        "document": "📁 Документ/Архив",
        "video": "🎬 Видео",
        "audio": "🎵 Аудио",
        "photo": "🖼️ Фотография",
        "voice": "🎤 Голосовое сообщение",
        "animation": "🎞️ GIF/Анимация"
    }
    
    await message.answer(
        f"✅ <b>Ссылка успешно создана!</b>\n\n"
        f"🏷 <b>Название:</b> {html.escape(name)}\n"
        f"📦 <b>Тип файла:</b> {type_names.get(file_type, 'Файл')}\n"
        f"♾ <b>Действие:</b> Бессрочная (неограниченно скачиваний)\n\n"
        f"🔗 <b>Ссылка для пользователей:</b>\n"
        f"<code>{deep_link}</code>\n\n"
        f"<i>Нажмите на ссылку, чтобы скопировать её.</i>",
        reply_markup=created_link_kb(bot_username, code, link_id),
        parse_mode="HTML"
    )
