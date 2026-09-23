from aiogram.fsm.state import State, StatesGroup


class ReviewStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_rating = State()
