from aiogram.fsm.state import State, StatesGroup


class NewGameFlow(StatesGroup):
    title = State()
    budget = State()
    date = State()


class JoinFlow(StatesGroup):
    name = State()
    wishes = State()


class EditFlow(StatesGroup):
    value = State()


class ChatFlow(StatesGroup):
    message = State()
