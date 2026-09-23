import time
import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("SleekCodeBot.Throttling")


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware для ограничения частоты запросов (Rate Limiting & Throttling).
    Защищает бота от флуда сообщениями, частых кликов по инлайн-кнопкам и DDoS-атак.
    """

    def __init__(self, rate_limit: float = 0.7, cleanup_interval: float = 300.0):
        """
        :param rate_limit: Минимальный интервал между запросами от одного пользователя (в секундах).
        :param cleanup_interval: Интервал очистки устаревших записей из кэша (в секундах).
        """
        super().__init__()
        self.rate_limit = rate_limit
        self.cleanup_interval = cleanup_interval
        # user_id -> timestamp последнего запроса
        self._user_last_action: Dict[int, float] = {}
        # user_id -> timestamp последнего отправленного предупреждения
        self._user_last_warning: Dict[int, float] = {}
        self._last_cleanup: float = time.monotonic()

    def _cleanup_old_records(self, now: float):
        """Периодическая очистка кэша от неактивных пользователей для экономии памяти."""
        if now - self._last_cleanup < self.cleanup_interval:
            return

        expire_threshold = now - (self.rate_limit * 10)
        # Очищаем действия
        stale_users = [
            uid for uid, ts in self._user_last_action.items() if ts < expire_threshold
        ]
        for uid in stale_users:
            self._user_last_action.pop(uid, None)

        # Очищаем предупреждения
        stale_warnings = [
            uid for uid, ts in self._user_last_warning.items() if ts < expire_threshold
        ]
        for uid in stale_warnings:
            self._user_last_warning.pop(uid, None)

        self._last_cleanup = now
        logger.debug("Очистка кэша троттлинга: удалено %d устаревших записей.", len(stale_users))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            # Если событие не от конкретного пользователя (сервисное обновление), пропускаем
            return await handler(event, data)

        user_id = user.id
        config = data.get("config")

        # Администраторы освобождаются от троттлинга
        if config and hasattr(config, "admin_ids") and user_id in config.admin_ids:
            return await handler(event, data)

        now = time.monotonic()
        self._cleanup_old_records(now)

        last_action = self._user_last_action.get(user_id, 0.0)
        elapsed = now - last_action

        if elapsed < self.rate_limit:
            # Превышение лимита запросов
            self._user_last_action[user_id] = now
            last_warning = self._user_last_warning.get(user_id, 0.0)

            # Для инлайн-кнопок: всплывающее аккуратное уведомление (alert)
            if isinstance(event, CallbackQuery):
                if now - last_warning > 1.0:
                    self._user_last_warning[user_id] = now
                    try:
                        await event.answer(
                            "⏳ Слишком много нажатий! Пожалуйста, не спешите.",
                            show_alert=True,
                        )
                    except Exception:
                        pass
                return None

            # Для обычных текстовых сообщений
            if isinstance(event, Message):
                # Отправляем предупреждение не чаще одного раза в 3 секунды
                if now - last_warning > 3.0:
                    self._user_last_warning[user_id] = now
                    try:
                        await event.answer(
                            "⏳ <b>Слишком частые запросы!</b>\n"
                            "Пожалуйста, подождите немного перед отправкой следующего сообщения."
                        )
                    except Exception:
                        pass
                logger.warning("Пользователь ID %s флудит сообщениями (троттлинг активирован).", user_id)
                return None

            return None

        # Лимит не превышен: обновляем время последнего действия и передаем обработку дальше
        self._user_last_action[user_id] = now
        return await handler(event, data)
