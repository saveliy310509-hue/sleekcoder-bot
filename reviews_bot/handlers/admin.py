import asyncio
import csv
import io
import logging
import re
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from config import Config
from buttons import (
    DEFAULT_BUTTONS,
    get_button_emoji_id,
    get_button_text,
    reset_all_buttons,
    reset_custom_button,
    set_custom_button,
)
from database.db import Database
from keyboards.admin_kb import (
    get_admin_menu_kb,
    get_back_to_admin_kb,
    get_blacklist_menu_kb,
    get_broadcast_confirm_kb,
    get_button_item_kb,
    get_buttons_menu_kb,
    get_cancel_state_kb,
    get_message_item_kb,
    get_messages_menu_kb,
    get_review_card_actions_kb,
    get_reviews_list_kb,
    get_welcome_settings_kb,
)
from keyboards.user_kb import get_start_kb
from messages import (
    DEFAULT_MESSAGES,
    get_message_template,
    reset_all_messages,
    reset_custom_message,
    set_custom_message,
)
from states.admin_states import AdminStates
from utils import extract_button_info, format_channel_post, format_stars, format_user_tag, get_star_display

logger = logging.getLogger(__name__)

admin_router = Router(name="admin_router")


class IsAdmin(BaseFilter):
    """Фильтр для проверки прав администратора."""

    async def __call__(self, event: Message | CallbackQuery, config: Config) -> bool:
        user = event.from_user
        if not user:
            return False
        return user.id in config.admin_ids


# Применяем фильтр IsAdmin ко всем обработчикам роутера
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())


# --- Главное меню админки ---


@admin_router.message(Command("admin"))
@admin_router.callback_query(F.data == "admin_panel")
@admin_router.callback_query(F.data == "admin:menu")
async def show_admin_panel(event: Message | CallbackQuery, state: FSMContext, db: Database):
    """Отображение главной панели администратора."""
    await state.clear()
    stats = await db.get_stats()

    text = (
        "👑 <b>Панель управления SleekCode Reviews</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"📝 Всего отзывов: <b>{stats['total_reviews']}</b>\n"
        f"⭐️ Средний рейтинг: <b>{stats['avg_rating']} / 5.0</b>\n"
        f"📅 Отзывов сегодня: <b>{stats['reviews_today']}</b>\n\n"
        "Выберите интересующий раздел:"
    )

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, reply_markup=get_admin_menu_kb())
    else:
        await event.answer(text, reply_markup=get_admin_menu_kb())


@admin_router.callback_query(F.data == "admin:close")
async def close_admin_panel(callback: CallbackQuery, state: FSMContext):
    """Закрытие админ-панели."""
    await state.clear()
    await callback.answer("Панель закрыта")
    await callback.message.delete()


@admin_router.callback_query(F.data == "admin:cancel_action")
async def cancel_admin_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия админа."""
    await state.clear()
    await callback.answer("Действие отменено")
    await callback.message.edit_text(
        "❌ Действие отменено.",
        reply_markup=get_back_to_admin_kb(),
    )


# --- Раздел: Статистика ---


@admin_router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery, db: Database):
    """Детальная статистика бота."""
    stats = await db.get_stats()
    stars = stats["stars_count"]
    total = stats["total_reviews"]

    def bar(count: int) -> str:
        if total == 0:
            return "░░░░░░░░░░ 0%"
        pct = int((count / total) * 100)
        filled = int(pct / 10)
        return f"{'█' * filled}{'░' * (10 - filled)} {pct}% ({count})"

    text = (
        "📊 <b>Детальная статистика отзывов:</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"📝 Всего отзывов: <b>{stats['total_reviews']}</b>\n"
        f"⭐️ Средняя оценка: <b>{stats['avg_rating']} / 5.0</b>\n"
        f"📅 Новых за сегодня: <b>{stats['reviews_today']}</b>\n"
        f"📢 Опубликовано в канал: <b>{stats['published_count']}</b>\n"
        f"🚫 Заблокировано спамеров: <b>{stats['banned_count']}</b>\n\n"
        "<b>Распределение по звёздам:</b>\n"
        f"⭐️ 5: {bar(stars.get(5, 0))}\n"
        f"⭐️ 4: {bar(stars.get(4, 0))}\n"
        f"⭐️ 3: {bar(stars.get(3, 0))}\n"
        f"⭐️ 2: {bar(stars.get(2, 0))}\n"
        f"⭐️ 1: {bar(stars.get(1, 0))}\n"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_back_to_admin_kb())


# --- Раздел: Просмотр и модерация отзывов ---


@admin_router.callback_query(F.data.startswith("admin:reviews:"))
async def browse_reviews(callback: CallbackQuery, db: Database):
    """Просмотр отзывов с пагинацией и фильтрацией."""
    parts = callback.data.split(":")
    current_index = int(parts[2])
    filter_type = parts[3] if len(parts) > 3 else "all"

    # Определение фильтра по рейтингу
    db_filter = None
    if filter_type in ("5", "4"):
        db_filter = int(filter_type)
    elif filter_type == "low":
        db_filter = "low"

    total_count = await db.count_reviews(db_filter)
    reviews = await db.get_reviews(limit=1, offset=current_index, rating_filter=db_filter)

    if total_count == 0 or not reviews:
        await callback.answer("Отзывов в этой категории не найдено", show_alert=True)
        text = (
            "📝 <b>Отзывы не найдены</b>\n\n"
            f"В категории «{filter_type}» пока нет ни одного отзыва."
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_reviews_list_kb(
                review_id=0,
                user_id=0,
                current_index=0,
                total_count=0,
                rating_filter=filter_type,
            ),
        )
        return

    rev = reviews[0]
    review_id = rev["id"]
    user_id = rev["user_id"]
    username = rev["username"]
    first_name = rev["first_name"]
    rating = rev["rating"]
    text_html = rev["text_html"]
    created_at = rev["created_at"]
    is_published = bool(rev["is_published"])
    admin_reply = rev.get("admin_reply")

    stars_str = await get_star_display(db, rating)
    user_tag = format_user_tag(user_id, username, first_name)
    pub_status = "✅ Опубликован в канал" if is_published else "⏳ Не опубликован"

    reply_block = ""
    if admin_reply:
        reply_block = f"\n\n💬 <b>Ответ администратора:</b>\n<i>{admin_reply}</i>"

    card_text = (
        f"📝 <b>Отзыв #{review_id}</b> ({current_index + 1} из {total_count})\n"
        f"⭐️ <b>Оценка:</b> {stars_str} ({rating}/5)\n"
        f"👤 <b>Автор:</b> {user_tag}\n"
        f"📅 <b>Дата:</b> {created_at}\n"
        f"📢 <b>Статус:</b> {pub_status}\n\n"
        f"<b>Текст отзыва:</b>\n{text_html}"
        f"{reply_block}"
    )

    await callback.answer()
    await callback.message.edit_text(
        card_text,
        reply_markup=get_reviews_list_kb(
            review_id=review_id,
            user_id=user_id,
            current_index=current_index,
            total_count=total_count,
            rating_filter=filter_type,
            is_published=is_published,
        ),
    )


# --- Действия над отзывами: Удаление ---


@admin_router.callback_query(F.data.startswith("admin:del_review:"))
async def delete_review_from_card(callback: CallbackQuery, db: Database):
    """Удаление отзыва по кнопке из карточки."""
    review_id = int(callback.data.split(":")[2])
    await db.delete_review(review_id)
    await callback.answer("Отзыв успешно удален из базы данных", show_alert=True)
    await callback.message.edit_text(
        f"🗑️ <b>Отзыв #{review_id} был удален администратором.</b>",
        reply_markup=None,
    )


@admin_router.callback_query(F.data.startswith("admin:del_list:"))
async def delete_review_from_list(callback: CallbackQuery, db: Database):
    """Удаление отзыва из списка при просмотре."""
    parts = callback.data.split(":")
    review_id = int(parts[2])
    current_index = int(parts[3])
    rating_filter = parts[4]

    await db.delete_review(review_id)
    await callback.answer("Отзыв удален!", show_alert=True)

    # Переходим к предыдущему или первому
    new_index = max(0, current_index - 1)
    callback.data = f"admin:reviews:{new_index}:{rating_filter}"
    await browse_reviews(callback, db)


# --- Действия над отзывами: Публикация в канал ---


async def get_effective_channel(db: Database, config: Config) -> Optional[str]:
    """Получение актуального канала для отзывов (из БД или config)."""
    db_channel = await db.get_setting("channel_id")
    if db_channel:
        return db_channel
    return config.reviews_channel_id


@admin_router.callback_query(F.data.startswith("admin:publish:"))
@admin_router.callback_query(F.data.startswith("admin:publish_list:"))
async def publish_review_to_channel(
    callback: CallbackQuery,
    db: Database,
    config: Config,
):
    """Публикация отзыва в настроенный Telegram-канал."""
    parts = callback.data.split(":")
    review_id = int(parts[2])

    channel_id = await get_effective_channel(db, config)
    if not channel_id:
        await callback.answer(
            "⚠️ Канал для публикации не настроен! Задайте его в «⚙️ Канал отзывов»",
            show_alert=True,
        )
        return

    rev = await db.get_review(review_id)
    if not rev:
        await callback.answer("Отзыв не найден!", show_alert=True)
        return

    stars_str = await get_star_display(db, rev["rating"])
    channel_text = format_channel_post(
        text_html=rev["text_html"],
        rating=rev["rating"],
        username=rev["username"],
        first_name=rev["first_name"],
        user_id=rev["user_id"],
        stars_display=stars_str,
    )

    try:
        await callback.bot.send_message(chat_id=channel_id, text=channel_text)
        await db.mark_published(review_id)
        await callback.answer("✅ Отзыв успешно опубликован в канал!", show_alert=True)

        if "publish_list" in parts[1]:
            # Обновляем клавиатуру в списке
            current_index = int(parts[3])
            rating_filter = parts[4]
            callback.data = f"admin:reviews:{current_index}:{rating_filter}"
            await browse_reviews(callback, db)
        else:
            # Обновляем инлайн-кнопку карточки
            await callback.message.edit_reply_markup(
                reply_markup=get_review_card_actions_kb(
                    review_id=review_id,
                    user_id=rev["user_id"],
                    is_published=True,
                )
            )
    except Exception as e:
        logger.error("Ошибка при публикации в канал %s: %s", channel_id, e)
        await callback.answer(
            f"❌ Ошибка публикации: убедитесь, что бот добавлен администратором в канал {channel_id}!",
            show_alert=True,
        )


# --- Действия над отзывами: Ответ пользователю ---


@admin_router.callback_query(F.data.startswith("admin:reply:"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext, db: Database):
    """Начало ответа пользователю на его отзыв."""
    review_id = int(callback.data.split(":")[2])
    rev = await db.get_review(review_id)
    if not rev:
        await callback.answer("Отзыв не найден!", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_reply_message)
    await state.update_data(
        target_review_id=review_id,
        target_user_id=rev["user_id"],
        review_text=rev["text_html"],
    )

    user_info = f"@{rev['username']}" if rev["username"] else f"ID {rev['user_id']}"
    text = (
        f"💬 <b>Ответ на отзыв #{review_id} (автор {user_info}):</b>\n\n"
        "Отправьте текст сообщения, которое получит пользователь от имени бота.\n"
        "<i>Поддерживается форматирование и эмодзи.</i>"
    )

    await callback.answer()
    await callback.message.answer(text, reply_markup=get_cancel_state_kb())


@admin_router.message(AdminStates.waiting_for_reply_message)
async def process_admin_reply_message(message: Message, state: FSMContext, db: Database):
    """Отправка ответа админа пользователю."""
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    target_review_id = data.get("target_review_id")
    review_text = data.get("review_text", "")

    reply_html = message.html_text or message.text or ""
    if not reply_html.strip():
        await message.answer("Пожалуйста, отправьте текстовый ответ.", reply_markup=get_cancel_state_kb())
        return

    await state.clear()

    # Сообщение пользователю
    user_msg = (
        "📩 <b>Ответ команды SleekCode на ваш отзыв:</b>\n\n"
        f"<blockquote>{review_text}</blockquote>\n\n"
        f"{reply_html}"
    )

    try:
        await message.bot.send_message(chat_id=target_user_id, text=user_msg)
        await db.save_admin_reply(target_review_id, reply_html)
        await message.answer(
            f"✅ <b>Ответ успешно доставлен пользователю!</b> (ID: {target_user_id})",
            reply_markup=get_back_to_admin_kb(),
        )
    except TelegramForbiddenError:
        await message.answer(
            f"❌ Не удалось доставить: пользователь {target_user_id} заблокировал бота.",
            reply_markup=get_back_to_admin_kb(),
        )
    except Exception as e:
        logger.error("Ошибка отправки ответа пользователю: %s", e)
        await message.answer(
            f"❌ Ошибка отправки: {e}",
            reply_markup=get_back_to_admin_kb(),
        )


# --- Раздел: Массовая рассылка ---


@admin_router.callback_query(F.data == "admin:broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext, db: Database):
    """Запуск мастера массовой рассылки."""
    total_users = (await db.get_stats())["total_users"]
    text = (
        "📢 <b>Массовая рассылка сообщений</b>\n\n"
        f"Получателей в базе: <b>{total_users}</b>\n\n"
        "Отправьте сообщение, которое хотите разослать всем пользователям.\n"
        "<i>Поддерживаются текст, премиум эмодзи, фото, видео и стикеры.</i>"
    )

    await state.set_state(AdminStates.waiting_for_broadcast_content)
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_cancel_state_kb())


@admin_router.message(AdminStates.waiting_for_broadcast_content)
async def preview_broadcast(message: Message, state: FSMContext, db: Database):
    """Предпросмотр сообщения для рассылки."""
    total_users = (await db.get_stats())["total_users"]

    await state.update_data(
        broadcast_chat_id=message.chat.id,
        broadcast_message_id=message.message_id,
    )
    await state.set_state(AdminStates.waiting_for_broadcast_confirm)

    await message.answer("👀 <b>Предпросмотр сообщения для рассылки:</b>")
    await message.copy_to(chat_id=message.chat.id)

    confirm_text = (
        f"❓ <b>Подтверждение рассылки</b>\n\n"
        f"Количество получателей: <b>{total_users}</b>\n"
        f"Вы действительно хотите отправить это сообщение всем пользователям?"
    )
    await message.answer(confirm_text, reply_markup=get_broadcast_confirm_kb())


@admin_router.callback_query(F.data == "admin:broadcast_cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки."""
    await state.clear()
    await callback.answer("Рассылка отменена")
    await callback.message.edit_text(
        "❌ <b>Рассылка была отменена.</b>",
        reply_markup=get_back_to_admin_kb(),
    )


@admin_router.callback_query(F.data == "admin:broadcast_start")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext, db: Database):
    """Выполнение рассылки всем пользователям с защитой от flood."""
    data = await state.get_data()
    from_chat_id = data.get("broadcast_chat_id")
    broadcast_msg_id = data.get("broadcast_message_id")

    await state.clear()
    await callback.answer("Рассылка запущена!")

    status_message = await callback.message.edit_text("🚀 <b>Рассылка выполняется...</b>\nПожалуйста, подождите.")

    users = await db.get_all_users()
    total = len(users)
    sent = 0
    blocked = 0
    failed = 0

    for user in users:
        uid = user["user_id"]
        # Не отправляем забаненным
        if user.get("is_banned"):
            continue

        try:
            await callback.bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=broadcast_msg_id,
            )
            sent += 1
            await asyncio.sleep(0.05)  # Защита от лимитов Telegram API
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await callback.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=from_chat_id,
                    message_id=broadcast_msg_id,
                )
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            logger.warning("Ошибка при рассылке пользователю %s: %s", uid, e)
            failed += 1

    report_text = (
        "✅ <b>Рассылка успешно завершена!</b>\n\n"
        f"📊 Всего пользователей: <b>{total}</b>\n"
        f"📨 Успешно доставлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"⚠️ Ошибок отправки: <b>{failed}</b>"
    )

    await status_message.edit_text(report_text, reply_markup=get_back_to_admin_kb())


# --- Раздел: Чёрный список ---


@admin_router.callback_query(F.data == "admin:blacklist")
async def show_blacklist_menu(callback: CallbackQuery, db: Database):
    """Меню управления чёрным списком."""
    banned_users = await db.get_banned_users()
    text = (
        "🚫 <b>Управление чёрным списком</b>\n\n"
        f"Всего заблокированных пользователей: <b>{len(banned_users)}</b>\n\n"
        "Заблокированные пользователи не могут отправлять отзывы."
    )
    await callback.answer()
    await callback.message.edit_text(
        text,
        reply_markup=get_blacklist_menu_kb(banned_count=len(banned_users)),
    )


@admin_router.callback_query(F.data.startswith("admin:ban_user:"))
async def ban_user_quick(callback: CallbackQuery, db: Database):
    """Быстрый бан автора отзыва по кнопке."""
    target_user_id = int(callback.data.split(":")[2])
    await db.ban_user(target_user_id, reason="Заблокирован администратором из карточки отзыва")
    await callback.answer(f"Пользователь {target_user_id} заблокирован!", show_alert=True)


@admin_router.callback_query(F.data == "admin:ban_by_id")
async def ask_ban_id(callback: CallbackQuery, state: FSMContext):
    """Запрос ID для блокировки."""
    await state.set_state(AdminStates.waiting_for_ban_id)
    await callback.answer()
    await callback.message.edit_text(
        "🚫 <b>Блокировка пользователя</b>\n\n"
        "Введите числовой <code>user_id</code> пользователя, которого хотите заблокировать:",
        reply_markup=get_cancel_state_kb(),
    )


@admin_router.message(AdminStates.waiting_for_ban_id)
async def process_ban_id(message: Message, state: FSMContext, db: Database):
    """Обработка введенного ID для блокировки."""
    raw_id = message.text.strip() if message.text else ""
    if not raw_id.isdigit():
        await message.answer("⚠️ Пожалуйста, введите корректный числовой ID пользователя:")
        return

    uid = int(raw_id)
    await db.ban_user(uid)
    await state.clear()
    await message.answer(
        f"✅ Пользователь с ID <code>{uid}</code> успешно заблокирован.",
        reply_markup=get_back_to_admin_kb(),
    )


@admin_router.callback_query(F.data == "admin:unban_by_id")
async def ask_unban_id(callback: CallbackQuery, state: FSMContext):
    """Запрос ID для разблокировки."""
    await state.set_state(AdminStates.waiting_for_unban_id)
    await callback.answer()
    await callback.message.edit_text(
        "🔓 <b>Разблокировка пользователя</b>\n\n"
        "Введите числовой <code>user_id</code> пользователя, которого хотите разблокировать:",
        reply_markup=get_cancel_state_kb(),
    )


@admin_router.message(AdminStates.waiting_for_unban_id)
async def process_unban_id(message: Message, state: FSMContext, db: Database):
    """Обработка разблокировки по ID."""
    raw_id = message.text.strip() if message.text else ""
    if not raw_id.isdigit():
        await message.answer("⚠️ Пожалуйста, введите корректный числовой ID пользователя:")
        return

    uid = int(raw_id)
    success = await db.unban_user(uid)
    await state.clear()
    if success:
        await message.answer(
            f"✅ Пользователь с ID <code>{uid}</code> разблокирован.",
            reply_markup=get_back_to_admin_kb(),
        )
    else:
        await message.answer(
            f"Пользователь с ID <code>{uid}</code> не был найден среди заблокированных.",
            reply_markup=get_back_to_admin_kb(),
        )


@admin_router.callback_query(F.data == "admin:banned_list")
async def show_banned_list(callback: CallbackQuery, db: Database):
    """Отображение списка заблокированных."""
    banned = await db.get_banned_users()
    if not banned:
        await callback.answer("Чёрный список пуст", show_alert=True)
        return

    lines = ["📋 <b>Список заблокированных пользователей:</b>\n"]
    for u in banned[:30]:
        username = f"@{u['username']}" if u.get("username") else "без юзернейма"
        lines.append(f"• ID: <code>{u['user_id']}</code> ({username}) — {u.get('ban_reason') or 'Бан'}")

    if len(banned) > 30:
        lines.append(f"\n<i>...и ещё {len(banned) - 30} пользователей.</i>")

    await callback.answer()
    await callback.message.edit_text("\n".join(lines), reply_markup=get_back_to_admin_kb())


# --- Раздел: Экспорт в CSV ---


@admin_router.callback_query(F.data == "admin:export")
async def export_reviews_csv(callback: CallbackQuery, db: Database):
    """Выгрузка всех отзывов в формате CSV (совместимом с Excel)."""
    await callback.answer("Формирую файл экспорта...")

    reviews = await db.get_reviews(limit=10000, offset=0)
    if not reviews:
        await callback.message.edit_text(
            "📝 В базе данных пока нет отзывов для экспорта.",
            reply_markup=get_back_to_admin_kb(),
        )
        return

    # Записываем CSV в память с BOM UTF-8 для корректного открытия в Excel
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)
    writer.writerow([
        "ID",
        "User ID",
        "Username",
        "Имя",
        "Оценка",
        "Текст отзыва",
        "Опубликовано в канал",
        "Ответ администратора",
        "Дата создания",
    ])

    for r in reviews:
        writer.writerow([
            r["id"],
            r["user_id"],
            r.get("username") or "",
            r.get("first_name") or "",
            r["rating"],
            r["text_html"],
            "Да" if r["is_published"] else "Нет",
            r.get("admin_reply") or "",
            r["created_at"],
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"reviews_export_{now_str}.csv"

    file = BufferedInputFile(csv_bytes, filename=filename)
    await callback.message.answer_document(
        document=file,
        caption=f"📥 <b>Экспорт отзывов SleekCode</b>\nВсего выгружено отзывов: <b>{len(reviews)}</b>",
    )
    await callback.message.edit_text(
        "✅ Файл экспорта сформирован и отправлен в чат.",
        reply_markup=get_back_to_admin_kb(),
    )


# --- Раздел: Настройки канала отзывов ---


@admin_router.callback_query(F.data == "admin:channel_settings")
async def show_channel_settings(
    callback: CallbackQuery,
    db: Database,
    config: Config,
):
    """Настройки канала для публикации отзывов."""
    current_channel = await get_effective_channel(db, config)
    status_str = f"<code>{current_channel}</code>" if current_channel else "<i>не установлен</i>"

    text = (
        "⚙️ <b>Настройки канала публикаций</b>\n\n"
        f"Текущий канал для отзывов: {status_str}\n\n"
        "Когда канал установлен, вы сможете в один клик публиковать проверенные отзывы в ваш публичный канал.\n\n"
        "<i>Бот должен быть добавлен администратором в канал с правом отправки сообщений!</i>"
    )

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить канал", callback_data="admin:set_channel")],
            [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="admin:menu")],
        ]
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=kb)


@admin_router.callback_query(F.data == "admin:set_channel")
async def ask_channel_id(callback: CallbackQuery, state: FSMContext):
    """Запрос нового канала."""
    await state.set_state(AdminStates.waiting_for_channel_id)
    await callback.answer()
    await callback.message.edit_text(
        "📢 <b>Установка канала отзывов</b>\n\n"
        "Отправьте username публичного канала (например, <code>@sleekcode_reviews</code>) "
        "или числовой ID (например, <code>-1001234567890</code>):\n\n"
        "<i>Не забудьте сначала сделать бота админом в этом канале!</i>",
        reply_markup=get_cancel_state_kb(),
    )


@admin_router.message(AdminStates.waiting_for_channel_id)
async def save_channel_id(message: Message, state: FSMContext, db: Database):
    """Сохранение нового канала отзывов."""
    channel_input = message.text.strip() if message.text else ""
    if not channel_input:
        await message.answer("Пожалуйста, отправьте username или ID канала:")
        return

    # Проверяем доступ бота к каналу
    try:
        chat = await message.bot.get_chat(channel_input)
        await db.set_setting("channel_id", str(chat.id))
        await state.clear()
        await message.answer(
            f"✅ <b>Канал успешно подключен!</b>\n"
            f"Название: <b>{chat.title}</b>\n"
            f"ID / Username: <code>{channel_input}</code>",
            reply_markup=get_back_to_admin_kb(),
        )
    except Exception as e:
        logger.error("Ошибка проверки канала %s: %s", channel_input, e)
        # Если get_chat не прошел, но админ уверен
        await db.set_setting("channel_id", channel_input)
        await state.clear()
        await message.answer(
            f"⚠️ Канал сохранен как <code>{channel_input}</code>, но бот пока не смог проверить к нему доступ.\n"
            "Убедитесь, что бот добавлен администратором канала.",
            reply_markup=get_back_to_admin_kb(),
        )


# --- Раздел: Редактирование приветственного сообщения ---


@admin_router.callback_query(F.data == "admin:welcome_settings")
async def show_welcome_settings(callback: CallbackQuery, db: Database):
    """Просмотр и настройки приветственного сообщения и кнопки."""
    custom_welcome = await db.get_setting("welcome_text")
    button_text = await db.get_setting("button_review_text") or "✍️ Оставить отзыв"
    button_emoji_id = await db.get_setting("button_review_emoji_id")

    if custom_welcome:
        status = f"🟢 <b>Установлен кастомный текст:</b>\n\n<blockquote>{custom_welcome}</blockquote>"
    else:
        status = (
            "⚪️ <b>Используется стандартный текст:</b>\n\n"
            "<blockquote>👋 <b>Здравствуйте, {name}!</b>\n\n"
            "Добро пожаловать в официального бота отзывов <b>SleekCode</b>.\n\n"
            "Здесь вы можете оставить свой честный отзыв о нашей работе. "
            "Вы можете написать любой текст, использовать форматирование и даже "
            "<b>премиум эмодзи</b> — мы бережно всё сохраним!\n\n"
            "Для того чтобы оставить отзыв, нажмите кнопку ниже или отправьте команду /review.</blockquote>"
        )

    if button_emoji_id:
        button_info = f"<tg-emoji id=\"{button_emoji_id}\">⭐️</tg-emoji> <code>{button_text}</code> (с Premium эмодзи)"
    else:
        button_info = f"<code>{button_text}</code>"

    text = (
        "✏️ <b>Настройка приветствия и кнопки (/start)</b>\n\n"
        f"{status}\n\n"
        f"🔘 <b>Кнопка отзыва:</b> {button_info}\n\n"
        "💡 <i>Все изменения применяются мгновенно, перезапуск бота не требуется!</i>"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_welcome_settings_kb())


@admin_router.callback_query(F.data == "admin:edit_welcome")
async def ask_new_welcome_text(callback: CallbackQuery, state: FSMContext):
    """Запрос нового приветственного текста."""
    await state.set_state(AdminStates.waiting_for_welcome_text)
    await callback.answer()
    await callback.message.edit_text(
        "✏️ <b>Введите новый текст приветственного сообщения:</b>\n\n"
        "Вы можете применить любое форматирование (жирный, курсив, премиум эмодзи, ссылки).\n"
        "Используйте <code>{name}</code> в месте, где хотите вставить имя пользователя.\n\n"
        "<i>Для отмены нажмите кнопку «❌ Отмена» ниже.</i>",
        reply_markup=get_cancel_state_kb(),
    )


@admin_router.message(AdminStates.waiting_for_welcome_text)
async def process_new_welcome_text(message: Message, state: FSMContext, db: Database):
    """Сохранение нового текста приветствия."""
    new_text = message.html_text or message.text or ""
    if not new_text.strip():
        await message.answer("Пожалуйста, отправьте текстовое сообщение.", reply_markup=get_cancel_state_kb())
        return

    await db.set_setting("welcome_text", new_text)
    await state.clear()

    preview = new_text.replace("{name}", message.from_user.first_name or "Пользователь")
    await message.answer(
        "✅ <b>Приветственное сообщение успешно обновлено!</b>\n\n"
        "<b>Предпросмотр (как увидит пользователь):</b>\n\n"
        f"{preview}",
        reply_markup=get_back_to_admin_kb(),
    )


# --- Раздел: Редактирование всех кнопок ---


@admin_router.callback_query(F.data == "admin:buttons_menu")
async def show_buttons_menu(callback: CallbackQuery):
    """Главное меню управления всеми кнопками бота."""
    text = (
        "🔘 <b>Управление текстами кнопок</b>\n\n"
        "Здесь вы можете изменить текст абсолютно любой кнопки в боте.\n"
        "⭐️ Для инлайн-кнопок поддерживаются <b>Premium эмодзи</b>!\n\n"
        "Выберите кнопку для настройки:"
    )
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_buttons_menu_kb())


@admin_router.callback_query(F.data.startswith("admin:btn:"))
async def show_button_item(callback: CallbackQuery, db: Database):
    """Просмотр настроек конкретной кнопки."""
    key = callback.data.split(":")[2]
    info = DEFAULT_BUTTONS.get(key)
    if not info:
        await callback.answer("Кнопка не найдена!", show_alert=True)
        return

    curr_text = await get_button_text(db, key)
    curr_emoji = await get_button_emoji_id(db, key)
    custom_saved = await db.get_setting(f"btn_text_{key}")
    is_custom = bool(custom_saved and custom_saved.strip())
    status = "🟢 <b>Установлен кастомный текст</b>" if is_custom else "⚪️ <b>Используется стандартный текст</b>"

    emoji_info = ""
    if info.get("supports_premium"):
        if curr_emoji:
            emoji_info = f"\n⭐️ <b>Premium эмодзи:</b> установлен (ID: <code>{curr_emoji}</code>)"
        else:
            emoji_info = "\n⭐️ <b>Premium эмодзи:</b> поддерживается (не установлен)"

    text = (
        f"🔘 <b>Настройка: {info['title']}</b>\n"
        f"<i>{info['desc']}</i>\n\n"
        f"{status}\n\n"
        f"Текущий текст: <code>{curr_text}</code>"
        f"{emoji_info}\n\n"
        "💡 <i>Все изменения применяются мгновенно, перезапуск бота не требуется!</i>"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_button_item_kb(key))


@admin_router.callback_query(F.data == "admin:edit_button")
@admin_router.callback_query(F.data.startswith("admin:btn_edit:"))
async def ask_new_button_text(callback: CallbackQuery, state: FSMContext, db: Database):
    """Запрос нового текста и эмодзи для кнопки."""
    if callback.data == "admin:edit_button":
        key = "start_review"
    else:
        key = callback.data.split(":")[2]

    info = DEFAULT_BUTTONS.get(key, {"title": "кнопки"})
    current_btn = await get_button_text(db, key)
    current_emoji = await get_button_emoji_id(db, key)
    await state.set_state(AdminStates.waiting_for_button_text)
    await state.update_data(target_btn_key=key)

    extra_info = f" (ID премиум эмодзи: <code>{current_emoji}</code>)" if current_emoji else ""
    premium_hint = (
        "\n⭐️ <b>Поддерживаются Premium эмодзи!</b> Вы можете вставить любой кастомный эмодзи из вашей подписки, и он станет иконкой кнопки.\n"
        if info.get("supports_premium")
        else ""
    )

    await callback.answer()
    await callback.message.edit_text(
        f"🔘 <b>Редактирование: {info.get('title', key)}</b>\n\n"
        f"Текущий текст: <code>{current_btn}</code>{extra_info}\n\n"
        "Отправьте сообщение с новым текстом для кнопки."
        f"{premium_hint}\n"
        "<i>Для отмены нажмите кнопку «❌ Отмена» ниже.</i>",
        reply_markup=get_cancel_state_kb(),
    )


@admin_router.message(AdminStates.waiting_for_button_text)
async def process_new_button_text(message: Message, state: FSMContext, db: Database):
    """Сохранение нового текста кнопки с поддержкой Premium эмодзи."""
    raw_text = message.text or ""
    if not raw_text.strip():
        await message.answer("Пожалуйста, отправьте текстовое сообщение для кнопки.", reply_markup=get_cancel_state_kb())
        return

    data = await state.get_data()
    key = data.get("target_btn_key") or "start_review"
    info = DEFAULT_BUTTONS.get(key, {})

    default_text = info.get("default", "")
    fallback_clean = re.sub(r"^[^\w\s]+", "", default_text).strip() or default_text
    cleaned_text, icon_emoji_id = extract_button_info(raw_text, message.entities, fallback_text=fallback_clean)
    # Если кнопка не поддерживает премиум, сохраняем только сырой текст
    if not info.get("supports_premium", False):
        icon_emoji_id = None
        cleaned_text = raw_text.strip()

    await set_custom_button(db, key, cleaned_text, icon_emoji_id)
    await state.clear()

    emoji_status = f"Да (ID: <code>{icon_emoji_id}</code>)" if icon_emoji_id else "Нет"

    # Формируем предпросмотр
    preview_kb = None
    if info.get("supports_premium"):
        preview_kb = get_start_kb(button_text=cleaned_text, icon_custom_emoji_id=icon_emoji_id)

    try:
        if preview_kb:
            await message.answer(
                f"✅ <b>Кнопка «{info.get('title', key)}» успешно обновлена!</b>\n\n"
                f"Текст: <code>{cleaned_text}</code>\n"
                f"Premium эмодзи: {emoji_status}\n\n"
                "<b>Предпросмотр кнопки:</b>",
                reply_markup=preview_kb,
            )
        else:
            await message.answer(
                f"✅ <b>Кнопка «{info.get('title', key)}» успешно обновлена!</b>\n\n"
                f"Новый текст: <code>{cleaned_text}</code>",
            )
    except Exception as e:
        logger.warning("Не удалось отправить превью с icon_custom_emoji_id: %s", e)
        await message.answer(
            f"✅ <b>Кнопка «{info.get('title', key)}» успешно обновлена!</b>\n\n"
            f"Текст: <code>{cleaned_text}</code>",
        )

    await message.answer(
        "Изменения вступили в силу мгновенно (перезапуск не нужен)!",
        reply_markup=get_back_to_admin_kb(),
    )


@admin_router.callback_query(F.data.startswith("admin:btn_reset:"))
async def reset_single_button(callback: CallbackQuery, db: Database):
    """Сброс конкретной кнопки по умолчанию."""
    key = callback.data.split(":")[2]
    await reset_custom_button(db, key)
    await callback.answer("Кнопка сброшена по умолчанию!", show_alert=True)
    callback.data = f"admin:btn:{key}"
    await show_button_item(callback, db)


@admin_router.callback_query(F.data == "admin:btn_reset_all")
async def reset_all_buttons_handler(callback: CallbackQuery, db: Database):
    """Сброс абсолютно всех кнопок по умолчанию."""
    await reset_all_buttons(db)
    await callback.answer("Все кнопки сброшены к стандартным!", show_alert=True)
    await show_buttons_menu(callback)


@admin_router.callback_query(F.data == "admin:reset_welcome")
async def reset_welcome_text(callback: CallbackQuery, db: Database):
    """Сброс текста приветствия и кнопки на стандартные."""
    await db.set_setting("welcome_text", "")
    await db.set_setting("button_review_text", "")
    await db.set_setting("button_review_emoji_id", "")
    await callback.answer("Текст и кнопка сброшены по умолчанию!", show_alert=True)
    await show_welcome_settings(callback, db)


# --- Раздел: Редактирование всех текстов и сообщений ---


@admin_router.callback_query(F.data == "admin:messages_menu")
async def show_messages_menu(callback: CallbackQuery):
    """Главное меню управления всеми сообщениями бота."""
    text = (
        "💬 <b>Управление текстами и сообщениями</b>\n\n"
        "Здесь вы можете изменить абсолютно любое сообщение бота.\n"
        "⭐️ <b>Поддерживаются Premium эмодзи</b> и любое форматирование!\n\n"
        "Выберите сообщение, которое хотите отредактировать:"
    )
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_messages_menu_kb())


@admin_router.callback_query(F.data.startswith("admin:msg:"))
async def show_message_item(callback: CallbackQuery, db: Database):
    """Просмотр конкретного сообщения."""
    key = callback.data.split(":")[2]
    info = DEFAULT_MESSAGES.get(key)
    if not info:
        await callback.answer("Сообщение не найдено!", show_alert=True)
        return

    template = await get_message_template(db, key)
    custom = await db.get_setting(f"msg_{key}")
    is_custom = bool(custom and custom.strip())
    status = "🟢 <b>Установлен кастомный текст</b>" if is_custom else "⚪️ <b>Используется стандартный текст</b>"

    placeholders_str = ""
    if info.get("placeholders"):
        tags = ", ".join(f"<code>{p}</code>" for p in info["placeholders"])
        placeholders_str = f"\n\n💡 <i>Доступные переменные: {tags}</i>"

    text = (
        f"📝 <b>{info['title']}</b>\n"
        f"<i>{info['desc']}</i>\n\n"
        f"{status}:\n\n"
        f"<blockquote>{template}</blockquote>"
        f"{placeholders_str}\n\n"
        "⭐️ <i>Поддерживаются Premium эмодзи, ссылки и HTML-разметка!</i>"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=get_message_item_kb(key))


@admin_router.callback_query(F.data.startswith("admin:msg_edit:"))
async def ask_edit_message(callback: CallbackQuery, state: FSMContext):
    """Запрос нового текста для выбранного сообщения."""
    key = callback.data.split(":")[2]
    info = DEFAULT_MESSAGES.get(key, {})
    await state.set_state(AdminStates.waiting_for_message_text)
    await state.update_data(target_msg_key=key)

    placeholders_str = ""
    if info.get("placeholders"):
        tags = ", ".join(f"<code>{p}</code>" for p in info["placeholders"])
        placeholders_str = f"\n💡 <i>Вы можете использовать переменные: {tags}</i>"

    await callback.answer()
    await callback.message.edit_text(
        f"✏️ <b>Редактирование: {info.get('title', key)}</b>\n\n"
        "Отправьте новое сообщение.\n"
        "⭐️ <b>Поддерживаются Premium эмодзи</b>, жирный/курсивный шрифт и ссылки!"
        f"{placeholders_str}\n\n"
        "<i>Для отмены нажмите «❌ Отмена» ниже.</i>",
        reply_markup=get_cancel_state_kb(),
    )


@admin_router.message(AdminStates.waiting_for_message_text)
async def process_save_custom_message(message: Message, state: FSMContext, db: Database):
    """Сохранение кастомного текста сообщения."""
    new_text = message.html_text or message.text or ""
    if not new_text.strip():
        await message.answer("Пожалуйста, отправьте текстовое сообщение.", reply_markup=get_cancel_state_kb())
        return

    data = await state.get_data()
    key = data.get("target_msg_key")
    if not key:
        await state.clear()
        await message.answer("Ошибка контекста.", reply_markup=get_back_to_admin_kb())
        return

    await set_custom_message(db, key, new_text)
    await state.clear()

    info = DEFAULT_MESSAGES.get(key, {})
    stars_sample = await get_star_display(db, 5)
    author_sample = f"@{message.from_user.username}" if message.from_user.username else f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
    preview = (
        new_text
        .replace("{name}", message.from_user.first_name or "Пользователь")
        .replace("{text}", "Отличный сервис, всё супер быстро и качественно! Рекомендую 👍")
        .replace("{stars}", stars_sample)
        .replace("{rating}", "5")
        .replace("{author}", author_sample)
        .replace("{user_id}", str(message.from_user.id))
    )

    await message.answer(
        f"✅ <b>Сообщение «{info.get('title', key)}» успешно сохранено!</b>\n\n"
        "<b>Предпросмотр:</b>\n\n"
        f"{preview}\n\n"
        "<i>Изменение вступило в силу мгновенно (перезапуск не нужен)!</i>",
        reply_markup=get_back_to_admin_kb(),
    )


@admin_router.callback_query(F.data.startswith("admin:msg_reset:"))
async def reset_single_message(callback: CallbackQuery, db: Database):
    """Сброс конкретного сообщения на стандартное."""
    key = callback.data.split(":")[2]
    await reset_custom_message(db, key)
    await callback.answer("Сообщение сброшено по умолчанию!", show_alert=True)
    callback.data = f"admin:msg:{key}"
    await show_message_item(callback, db)


@admin_router.callback_query(F.data == "admin:msg_reset_all")
async def reset_all_messages_handler(callback: CallbackQuery, db: Database):
    """Сброс всех сообщений бота по умолчанию."""
    await reset_all_messages(db)
    await callback.answer("Все сообщения и кнопка сброшены к стандартным!", show_alert=True)
    await show_messages_menu(callback)


@admin_router.callback_query(F.data == "admin:noop")
async def noop_handler(callback: CallbackQuery):
    """Пустой обработчик для информационных кнопок."""
    await callback.answer()
