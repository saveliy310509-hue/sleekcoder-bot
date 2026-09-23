from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    waiting_for_reply_message = State()
    waiting_for_broadcast_content = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()
    waiting_for_channel_id = State()
    waiting_for_welcome_text = State()
    waiting_for_button_text = State()
    waiting_for_message_text = State()
