"""Участник: вступление по ссылке, карточка игры и изменение анкеты."""

from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import keyboards as kb
from bot.db import Database, Game, GameClosed, Participant
from bot.states import EditFlow, JoinFlow
from bot.views import TEXTS, assignment, clean_text, game_info, participant_card

router = Router()

LIMITS = {"name": config.MAX_NAME_LEN, "wishes": config.MAX_WISHES_LEN}


async def membership(call: CallbackQuery, db: Database, game_id: int) -> tuple[Game, Participant] | None:
    """Игра и анкета нажавшего кнопку или None (с ответом «кнопка устарела»)."""
    game = await db.get_game(game_id)
    me = await db.get_participant(game_id, call.from_user.id) if game else None
    if game is None or me is None:
        await call.answer(TEXTS["stale_button"], show_alert=True)
        return None
    return game, me


async def _card(db: Database, game: Game, me: Participant) -> str:
    receiver = await db.get_participant(game.id, me.receiver_id) if me.receiver_id else None
    return participant_card(game, me, receiver)


async def _send_card(message: Message, db: Database, game: Game, me: Participant) -> None:
    await message.answer(await _card(db, game, me), reply_markup=kb.participant_menu(game))


# --- Вступление --------------------------------------------------------------


async def begin_join(message: Message, state: FSMContext, db: Database, code: str) -> None:
    game = await db.get_game_by_code(code)
    if game is None:
        await message.answer(TEXTS["invalid_link"], reply_markup=kb.main_menu())
        return
    me = await db.get_participant(game.id, message.from_user.id)
    if me is not None:
        await message.answer(TEXTS["already_joined"], reply_markup=kb.main_menu())
        await _send_card(message, db, game, me)
        return
    if not game.is_open:
        await message.answer(TEXTS["game_started"], reply_markup=kb.main_menu())
        return
    await state.set_state(JoinFlow.name)
    await state.update_data(game_id=game.id)
    await message.answer(TEXTS["join_intro"].format(info=game_info(game)), reply_markup=kb.main_menu())
    await message.answer(TEXTS["ask_name"], reply_markup=kb.cancel())


@router.message(JoinFlow.name, kb.FREE_TEXT)
async def got_name(message: Message, state: FSMContext) -> None:
    name = clean_text(message.text, config.MAX_NAME_LEN)
    if name is None:
        await message.answer(TEXTS["bad_name"].format(max=config.MAX_NAME_LEN))
        return
    await state.update_data(name=name)
    await state.set_state(JoinFlow.wishes)
    await message.answer(TEXTS["ask_wishes"], reply_markup=kb.cancel())


@router.message(JoinFlow.wishes, kb.FREE_TEXT)
async def got_wishes(message: Message, state: FSMContext, db: Database) -> None:
    wishes = clean_text(message.text, config.MAX_WISHES_LEN)
    if wishes is None:
        await message.answer(TEXTS["bad_wishes"].format(max=config.MAX_WISHES_LEN))
        return
    data = await state.get_data()
    await state.clear()
    try:
        await db.add_participant(data["game_id"], message.from_user.id, data["name"], wishes)
    except GameClosed:
        await message.answer(TEXTS["game_started"], reply_markup=kb.main_menu())
        return
    game = await db.get_game(data["game_id"])
    await message.answer(TEXTS["joined"].format(title=game.title), reply_markup=kb.main_menu())


# --- Мои участия -------------------------------------------------------------


@router.message(F.text == TEXTS["btn_participation"])
async def my_participation(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    games = await db.participant_games(message.from_user.id)
    if not games:
        await message.answer(TEXTS["not_participant"])
    elif len(games) == 1:
        me = await db.get_participant(games[0].id, message.from_user.id)
        await _send_card(message, db, games[0], me)
    else:
        await message.answer(TEXTS["choose_game"], reply_markup=kb.participant_games(games))


@router.callback_query(kb.MyGameCb.filter())
async def game_card(call: CallbackQuery, callback_data: kb.MyGameCb, db: Database) -> None:
    found = await membership(call, db, callback_data.id)
    if found is None:
        return
    game, me = found
    await call.message.edit_text(await _card(db, game, me), reply_markup=kb.participant_menu(game))
    await call.answer()


# --- Изменение анкеты --------------------------------------------------------


@router.callback_query(kb.EditCb.filter())
async def edit(call: CallbackQuery, callback_data: kb.EditCb, state: FSMContext, db: Database) -> None:
    if await membership(call, db, callback_data.game_id) is None:
        return
    await state.set_state(EditFlow.value)
    await state.update_data(game_id=callback_data.game_id, field=callback_data.field)
    await call.message.answer(TEXTS[f"ask_{callback_data.field}"], reply_markup=kb.cancel())
    await call.answer()


@router.message(EditFlow.value, kb.FREE_TEXT)
async def got_edit(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    field = data["field"]
    value = clean_text(message.text, LIMITS[field])
    if value is None:
        await message.answer(TEXTS[f"bad_{field}"].format(max=LIMITS[field]))
        return
    await state.clear()
    game = await db.get_game(data["game_id"])
    if game is None or await db.get_participant(game.id, message.from_user.id) is None:
        await message.answer(TEXTS["stale_button"], reply_markup=kb.main_menu())
        return
    await db.update_participant(game.id, message.from_user.id, field, value)
    me = await db.get_participant(game.id, message.from_user.id)

    # Санта уже получил анкету в личку — сообщим ему об изменениях.
    santa = await db.santa_of(game.id, me.user_id)
    if santa is not None:
        with suppress(TelegramAPIError):
            await bot.send_message(
                santa.user_id, TEXTS["profile_updated"].format(title=game.title, assignment=assignment(me))
            )

    await message.answer(TEXTS["saved"], reply_markup=kb.main_menu())
    await _send_card(message, db, game, me)
