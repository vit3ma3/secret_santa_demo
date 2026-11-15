from aiogram import F
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Game, Participant
from bot.views import TEXTS, fmt_date

CANCEL_FLOW = "cancel_flow"
TO_RECEIVER = "receiver"
TO_SANTA = "santa"

MENU_BUTTONS = {TEXTS[key] for key in ("btn_new_game", "btn_my_games", "btn_participation")}
# Любое сообщение, кроме кнопки меню и команды.
NOT_MENU = ~F.text.in_(MENU_BUTTONS) & ~F.text.startswith("/")
# Текст, введённый на шаге сценария.
FREE_TEXT = F.text & NOT_MENU


class GameCb(CallbackData, prefix="g"):
    action: str  # card | members | excl | draw | draw_ok
    id: int


class KickCb(CallbackData, prefix="kick"):
    game_id: int
    user_id: int


class ExclCb(CallbackData, prefix="ex"):
    action: str  # add | del
    game_id: int
    a: int = 0
    b: int = 0


class MyGameCb(CallbackData, prefix="my"):
    id: int


class EditCb(CallbackData, prefix="edit"):
    game_id: int
    field: str  # name | wishes


class ChatCb(CallbackData, prefix="chat"):
    game_id: int
    to: str  # receiver | santa


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS["btn_new_game"])],
            [KeyboardButton(text=TEXTS["btn_my_games"]), KeyboardButton(text=TEXTS["btn_participation"])],
        ],
        resize_keyboard=True,
    )


def cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=TEXTS["btn_cancel_flow"], callback_data=CANCEL_FLOW)]]
    )


def _with_back(
    builder: InlineKeyboardBuilder, game_id: int, *row_sizes: int, to: str = "card"
) -> InlineKeyboardMarkup:
    builder.adjust(*(row_sizes or (1,)))
    builder.row(
        InlineKeyboardButton(text=TEXTS["btn_back"], callback_data=GameCb(action=to, id=game_id).pack())
    )
    return builder.as_markup()


# --- Организатор -------------------------------------------------------------


def organizer_games(games: list[Game]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game in games:
        builder.button(
            text=f"{game.title} · {fmt_date(game.exchange_date)}", callback_data=GameCb(action="card", id=game.id)
        )
    builder.adjust(1)
    return builder.as_markup()


def game_menu(game: Game) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_members"], callback_data=GameCb(action="members", id=game.id))
    builder.button(text=TEXTS["btn_exclusions"], callback_data=GameCb(action="excl", id=game.id))
    if game.is_open:
        builder.button(text=TEXTS["btn_draw"], callback_data=GameCb(action="draw", id=game.id))
    builder.adjust(2, 1)
    return builder.as_markup()


def back(game_id: int) -> InlineKeyboardMarkup:
    return _with_back(InlineKeyboardBuilder(), game_id)


def members(game: Game, people: list[Participant]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if game.is_open:
        for person in people:
            builder.button(text=f"❌ {person.name}", callback_data=KickCb(game_id=game.id, user_id=person.user_id))
    return _with_back(builder, game.id, 2)


def exclusions(game: Game, pairs: list[tuple[int, int]], names: dict[int, str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if game.is_open:
        for a, b in pairs:
            builder.button(
                text=f"🗑 {names[a]} ↔ {names[b]}", callback_data=ExclCb(action="del", game_id=game.id, a=a, b=b)
            )
        builder.button(text=TEXTS["btn_add_excl"], callback_data=ExclCb(action="add", game_id=game.id))
    return _with_back(builder, game.id)


def pick_for_exclusion(game_id: int, candidates: list[Participant], first: int) -> InlineKeyboardMarkup:
    """Выбор первого участника пары (first == 0) или второго."""
    builder = InlineKeyboardBuilder()
    for person in candidates:
        if first:
            data = ExclCb(action="add", game_id=game_id, a=first, b=person.user_id)
        else:
            data = ExclCb(action="add", game_id=game_id, a=person.user_id)
        builder.button(text=person.name, callback_data=data)
    return _with_back(builder, game_id, 2, to="excl")


def draw_confirm(game_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_draw_ok"], callback_data=GameCb(action="draw_ok", id=game_id))
    return _with_back(builder, game_id)


# --- Участник ----------------------------------------------------------------


def participant_games(games: list[Game]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game in games:
        builder.button(text=f"{game.title} · {fmt_date(game.exchange_date)}", callback_data=MyGameCb(id=game.id))
    builder.adjust(1)
    return builder.as_markup()


def participant_menu(game: Game) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_edit_name"], callback_data=EditCb(game_id=game.id, field="name"))
    builder.button(text=TEXTS["btn_edit_wishes"], callback_data=EditCb(game_id=game.id, field="wishes"))
    if not game.is_open:
        builder.button(text=TEXTS["btn_chat_receiver"], callback_data=ChatCb(game_id=game.id, to=TO_RECEIVER))
        builder.button(text=TEXTS["btn_chat_santa"], callback_data=ChatCb(game_id=game.id, to=TO_SANTA))
    builder.adjust(2)
    return builder.as_markup()


def chat_buttons(game_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_chat_receiver"], callback_data=ChatCb(game_id=game_id, to=TO_RECEIVER))
    builder.button(text=TEXTS["btn_chat_santa"], callback_data=ChatCb(game_id=game_id, to=TO_SANTA))
    builder.adjust(1)
    return builder.as_markup()


def reply(game_id: int, to: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_reply"], callback_data=ChatCb(game_id=game_id, to=to))
    return builder.as_markup()
