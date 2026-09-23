import logging
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from buttons import (
    build_cancel_kb,
    build_rating_kb,
    build_review_card_actions_kb,
    build_start_kb,
    get_button_text,
)
from config import Config
from database.db import Database
from keyboards.user_kb import remove_kb
from messages import render_message
from states.user_states import ReviewStates
from utils import (
    format_review_message,
    format_stars,
    get_star_display,
    parse_rating,
    render_admin_review_message,
)

logger = logging.getLogger(__name__)

user_router = Router(name="user_router")


@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, config: Config):
    """Обработчик команды /start."""
    await state.clear()

    user = message.from_user
    if not user:
        return

    # Регистрируем/обновляем пользователя в базе
    await db.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )

    # Проверяем бан
    if await db.is_banned(user.id):
        banned_msg = await render_message(db, "banned")
        await message.answer(banned_msg, reply_markup=remove_kb())
        return

    # Получаем приветственное сообщение и клавиатуру
    welcome_text = await render_message(db, "welcome", name=user.first_name or "друг")
    start_kb = await build_start_kb(db)

    await message.answer(welcome_text, reply_markup=start_kb)


@user_router.message(Command("review"))
@user_router.callback_query(F.data == "start_review")
async def process_start_review(event: Message | CallbackQuery, state: FSMContext, db: Database):
    """Начало процесса оставления отзыва."""
    user = event.from_user
    if not user:
        return

    if await db.is_banned(user.id):
        text = await render_message(db, "banned")
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return

    prompt_text = await render_message(db, "review_prompt")
    cancel_kb = await build_cancel_kb(db)

    await state.set_state(ReviewStates.waiting_for_text)

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(prompt_text, reply_markup=cancel_kb)
    else:
        await event.answer(prompt_text, reply_markup=cancel_kb)


@user_router.callback_query(F.data == "user_cancel")
async def process_inline_cancel(callback: CallbackQuery, state: FSMContext, db: Database):
    """Отмена отправки отзыва по нажатию инлайн-кнопки."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        cancel_text = await render_message(db, "cancel")
        try:
            await callback.message.edit_text(cancel_text)
        except Exception:
            await callback.message.answer(cancel_text)
    else:
        try:
            await callback.message.edit_text("Действие отменено.")
        except Exception:
            pass
    await callback.answer()


@user_router.message(Command("cancel"))
async def process_cancel_cmd(message: Message, state: FSMContext, db: Database):
    """Отмена отправки отзыва по команде."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активных действий для отмены.", reply_markup=remove_kb())
        return

    await state.clear()
    cancel_text = await render_message(db, "cancel")
    await message.answer(cancel_text, reply_markup=remove_kb())


@user_router.message(ReviewStates.waiting_for_text)
async def process_review_text(message: Message, state: FSMContext, db: Database):
    """Получение текста отзыва (с сохранением HTML и премиум эмодзи)."""
    user = message.from_user
    if not user:
        return

    # Проверка отмены
    cancel_btn = await get_button_text(db, "cancel")
    if message.text and message.text.strip() in (cancel_btn.strip(), "❌ Отмена", "/cancel"):
        await state.clear()
        cancel_text = await render_message(db, "cancel")
        await message.answer(cancel_text, reply_markup=remove_kb())
        return

    if await db.is_banned(user.id):
        await state.clear()
        banned_msg = await render_message(db, "banned")
        await message.answer(banned_msg, reply_markup=remove_kb())
        return

    # Получаем HTML-текст (содержит <tg-emoji id="..."> для премиум эмодзи)
    text_html = message.html_text or message.text or ""
    if not text_html.strip():
        cancel_kb = await build_cancel_kb(db)
        await message.answer(
            "⚠️ Пожалуйста, отправьте текстовое сообщение с вашим отзывом.",
            reply_markup=cancel_kb,
        )
        return

    # Сохраняем в контекст FSM
    await state.update_data(text_html=text_html)
    await state.set_state(ReviewStates.waiting_for_rating)

    rating_prompt = await render_message(db, "rating_prompt")
    rating_kb = await build_rating_kb(db)
    await message.answer(rating_prompt, reply_markup=rating_kb)


@user_router.callback_query(ReviewStates.waiting_for_rating, F.data.startswith("rate:"))
async def process_inline_rating(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    config: Config,
):
    """Обработка нажатия на инлайн-кнопку оценки (1-5 звёзд) с поддержкой Premium эмодзи."""
    user = callback.from_user
    if not user:
        await callback.answer()
        return

    try:
        rating = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        rating = 5

    data = await state.get_data()
    text_html = data.get("text_html", "")
    await state.clear()

    # Сохраняем отзыв в базу данных
    review_id = await db.add_review(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        text_html=text_html,
        rating=rating,
    )

    stars_str = await get_star_display(db, rating)

    success_text = await render_message(
        db,
        "review_success",
        stars=stars_str,
        rating=rating,
    )
    try:
        await callback.message.edit_text(success_text)
    except Exception:
        await callback.message.answer(success_text)
    await callback.answer()

    # Формируем настраиваемое сообщение для администратора с премиум-звёздами
    admin_message_text = await render_admin_review_message(
        db=db,
        text_html=text_html,
        rating=rating,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    card_keyboard = await build_review_card_actions_kb(
        db=db,
        review_id=review_id,
        user_id=user.id,
        is_published=False,
    )

    for admin_id in config.admin_ids:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=admin_message_text,
                reply_markup=card_keyboard,
            )
        except Exception as e:
            logger.warning("Не удалось отправить уведомление админу %s: %s", admin_id, e)


@user_router.callback_query(F.data.startswith("rate:"))
async def process_expired_rating(callback: CallbackQuery):
    """Обработка устаревшей кнопки оценки."""
    await callback.answer("Оценка уже сохранена или время сессии истекло.", show_alert=True)


@user_router.message(ReviewStates.waiting_for_rating)
async def process_review_rating(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
):
    """Получение оценки от 1 до 5 звезд и отправка отзыва админу."""
    user = message.from_user
    if not user:
        return

    # Проверка отмены
    cancel_btn = await get_button_text(db, "cancel")
    if message.text and message.text.strip() in (cancel_btn.strip(), "❌ Отмена", "/cancel"):
        await state.clear()
        cancel_text = await render_message(db, "cancel")
        await message.answer(cancel_text, reply_markup=remove_kb())
        return

    if not message.text:
        rating_kb = await build_rating_kb(db)
        await message.answer(
            "Пожалуйста, выберите оценку от 1 до 5 на клавиатуре снизу 👇",
            reply_markup=rating_kb,
        )
        return

    # Проверяем соответствие кастомным кнопкам оценок
    rating = None
    for r in range(1, 6):
        btn_val = await get_button_text(db, f"rate_{r}")
        if message.text.strip() == btn_val.strip():
            rating = r
            break

    # Если не совпало с кастомной кнопкой, пробуем стандартный парсер
    if not rating:
        rating = parse_rating(message.text)

    if not rating:
        rating_kb = await build_rating_kb(db)
        await message.answer(
            "⚠️ Пожалуйста, выберите оценку от 1 до 5 звёзд на клавиатуре снизу 👇",
            reply_markup=rating_kb,
        )
        return

    data = await state.get_data()
    text_html = data.get("text_html", "")
    await state.clear()

    # Сохраняем отзыв в базу данных
    review_id = await db.add_review(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        text_html=text_html,
        rating=rating,
    )

    stars_str = await get_star_display(db, rating)

    # Благодарим пользователя и скрываем клавиатуру
    success_text = await render_message(
        db,
        "review_success",
        stars=stars_str,
        rating=rating,
    )
    await message.answer(success_text, reply_markup=remove_kb())

    # Формируем настраиваемое сообщение для администратора с премиум-звёздами
    admin_message_text = await render_admin_review_message(
        db=db,
        text_html=text_html,
        rating=rating,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    card_keyboard = await build_review_card_actions_kb(
        db=db,
        review_id=review_id,
        user_id=user.id,
        is_published=False,
    )

    # Отправляем всем администраторам бота
    for admin_id in config.admin_ids:
        try:
            await message.bot.send_message(
                chat_id=admin_id,
                text=admin_message_text,
                reply_markup=card_keyboard,
            )
        except Exception as e:
            logger.warning("Не удалось отправить уведомление админу %s: %s", admin_id, e)
