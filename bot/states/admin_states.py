from aiogram.fsm.state import State, StatesGroup

class CreateLinkState(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()

class EditTextState(StatesGroup):
    waiting_for_new_text = State()

class ChangeFileState(StatesGroup):
    waiting_for_new_file = State()

class ChangeCaptionState(StatesGroup):
    waiting_for_new_caption = State()

class ChangeNameState(StatesGroup):
    waiting_for_new_name = State()
