"""Организатор: создание игры, участники, исключения и жеребьёвка."""

import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import config
from bot import keyboards as kb
from bot.db import Database, Game, GameClosed
from bot.draw import DrawImpossible
from bot.states import NewGameFlow
from bot.views import TEXTS, assignment, clean_text, game_info, organizer_card, parse_date, today

logger = logging.getLogger(__name__)
router = Router()


# --- Создание игры -----------------------------------------------------------


@router.message(F.text == TEXTS["btn_new_game"])
async def new_game(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewGameFlow.title)
    await message.answer(TEXTS["ask_title"], reply_markup=kb.cancel())


@router.message(NewGameFlow.title, kb.FREE_TEXT)
async def got_title(message: Message, state: FSMContext) -> None:
    title = clean_text(message.text, config.MAX_TITLE_LEN)
    if title is None:
        await message.answer(TEXTS["bad_title"].format(max=config.MAX_TITLE_LEN))
        return
    await state.update_data(title=title)
    await state.set_state(NewGameFlow.budget)
    await message.answer(TEXTS["ask_budget"], reply_markup=kb.cancel())


@router.message(NewGameFlow.budget, kb.FREE_TEXT)
async def got_budget(message: Message, state: FSMContext) -> None:
    budget = clean_text(message.text, config.MAX_BUDGET_LEN)
    if budget is None:
        await message.answer(TEXTS["bad_budget"].format(max=config.MAX_BUDGET_LEN))
        return
    await state.update_data(budget=budget)
    await state.set_state(NewGameFlow.date)
    await message.answer(TEXTS["ask_date"], reply_markup=kb.cancel())


@router.message(NewGameFlow.date, kb.FREE_TEXT)
async def got_date(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    day = parse_date(message.text)
    if day is None:
        await message.answer(TEXTS["bad_date"])
        return
    if day <= today():
        await message.answer(TEXTS["date_in_past"])
        return
    data = await state.get_data()
    await state.clear()
    game = await db.create_game(message.from_user.id, data["title"], data["budget"], day)
    await message.answer(TEXTS["game_created"], reply_markup=kb.main_menu())
    await message.answer(await organizer_card(bot, game, 0), reply_markup=kb.game_menu(game))


# --- Мои игры ----------------------------------------------------------------


@router.message(F.text == TEXTS["btn_my_games"])
async def my_games(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    games = await db.organizer_games(message.from_user.id)
    if not games:
        await message.answer(TEXTS["no_games"])
        return
    await message.answer(TEXTS["my_games"], reply_markup=kb.organizer_games(games))


async def _own_game(call: CallbackQuery, db: Database, game_id: int) -> Game | None:
    game = await db.get_game(game_id)
    if game is None or game.organizer_id != call.from_user.id:
        await call.answer(TEXTS["stale_button"], show_alert=True)
        return None
    return game


async def _edit(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    # Telegram отвечает ошибкой, если текст и кнопки не изменились.
    with suppress(TelegramBadRequest):
        await call.message.edit_text(text, reply_markup=markup)


@router.callback_query(kb.GameCb.filter(F.action == "card"))
async def game_card(call: CallbackQuery, callback_data: kb.GameCb, db: Database, bot: Bot) -> None:
    game = await _own_game(call, db, callback_data.id)
    if game is None:
        return
    count = len(await db.participants(game.id))
    await _edit(call, await organizer_card(bot, game, count), kb.game_menu(game))
    await call.answer()


# --- Участники ---------------------------------------------------------------


async def _show_members(call: CallbackQuery, db: Database, game: Game) -> None:
    people = await db.participants(game.id)
    if people:
        text = TEXTS["members_header"].format(title=game.title)
        text += "\n".join(f"{i}. {person.name}" for i, person in enumerate(people, 1))
        if game.is_open:
            text += "\n\n" + TEXTS["members_kick_hint"]
    else:
        text = TEXTS["members_empty"]
    await _edit(call, text, kb.members(game, people))


@router.callback_query(kb.GameCb.filter(F.action == "members"))
async def members(call: CallbackQuery, callback_data: kb.GameCb, db: Database) -> None:
    game = await _own_game(call, db, callback_data.id)
    if game is None:
        return
    await _show_members(call, db, game)
    await call.answer()


@router.callback_query(kb.KickCb.filter())
async def kick(call: CallbackQuery, callback_data: kb.KickCb, db: Database, bot: Bot) -> None:
    game = await _own_game(call, db, callback_data.game_id)
    if game is None:
        return
    person = await db.get_participant(game.id, callback_data.user_id)
    try:
        await db.remove_participant(game.id, callback_data.user_id)
    except GameClosed:
        await call.answer(TEXTS["game_closed"], show_alert=True)
        return
    if person is None:
        await call.answer()
    else:
        await call.answer(TEXTS["kicked"].format(name=person.name))
        with suppress(TelegramAPIError):
            await bot.send_message(person.user_id, TEXTS["you_were_kicked"].format(title=game.title))
    await _show_members(call, db, game)


# --- Исключения --------------------------------------------------------------


async def _show_exclusions(call: CallbackQuery, db: Database, game: Game) -> None:
    names = {person.user_id: person.name for person in await db.participants(game.id)}
    pairs = await db.exclusions(game.id)
    if pairs:
        text = TEXTS["excl_header"] + "\n".join(f"{names[a]} ↔ {names[b]}" for a, b in pairs)
    else:
        text = TEXTS["excl_empty"]
    await _edit(call, text, kb.exclusions(game, pairs, names))


@router.callback_query(kb.GameCb.filter(F.action == "excl"))
async def exclusions(call: CallbackQuery, callback_data: kb.GameCb, db: Database) -> None:
    game = await _own_game(call, db, callback_data.id)
    if game is None:
        return
    await _show_exclusions(call, db, game)
    await call.answer()


@router.callback_query(kb.ExclCb.filter(F.action == "add"))
async def add_exclusion(call: CallbackQuery, callback_data: kb.ExclCb, db: Database) -> None:
    """Добавление пары в три нажатия: кнопка → первый участник → второй."""
    game = await _own_game(call, db, callback_data.game_id)
    if game is None:
        return
    if not game.is_open:
        await call.answer(TEXTS["game_closed"], show_alert=True)
        return
    people = await db.participants(game.id)
    names = {person.user_id: person.name for person in people}
    a, b = callback_data.a, callback_data.b
    if (a and a not in names) or (b and b not in names):
        await call.answer(TEXTS["stale_button"], show_alert=True)
        return

    if a and b:
        try:
            await db.add_exclusion(game.id, a, b)
        except GameClosed:
            await call.answer(TEXTS["game_closed"], show_alert=True)
            return
        await _show_exclusions(call, db, game)
        await call.answer()
        return

    if a:
        paired = {x for pair in await db.exclusions(game.id) if a in pair for x in pair}
        candidates = [person for person in people if person.user_id != a and person.user_id not in paired]
        text = TEXTS["excl_pick_second"].format(name=names[a])
    else:
        candidates = people if len(people) >= 2 else []
        text = TEXTS["excl_pick_first"]
    if not candidates:
        await call.answer(TEXTS["excl_no_candidates"], show_alert=True)
        return
    await _edit(call, text, kb.pick_for_exclusion(game.id, candidates, a))
    await call.answer()


@router.callback_query(kb.ExclCb.filter(F.action == "del"))
async def delete_exclusion(call: CallbackQuery, callback_data: kb.ExclCb, db: Database) -> None:
    game = await _own_game(call, db, callback_data.game_id)
    if game is None:
        return
    try:
        await db.delete_exclusion(game.id, callback_data.a, callback_data.b)
    except GameClosed:
        await call.answer(TEXTS["game_closed"], show_alert=True)
        return
    await _show_exclusions(call, db, game)
    await call.answer()


# --- Жеребьёвка --------------------------------------------------------------


@router.callback_query(kb.GameCb.filter(F.action == "draw"))
async def draw_confirm(call: CallbackQuery, callback_data: kb.GameCb, db: Database) -> None:
    game = await _own_game(call, db, callback_data.id)
    if game is None:
        return
    if not game.is_open:
        await call.answer(TEXTS["game_closed"], show_alert=True)
        return
    count = len(await db.participants(game.id))
    if count < config.MIN_PARTICIPANTS:
        await call.answer(TEXTS["too_few"].format(min=config.MIN_PARTICIPANTS, count=count), show_alert=True)
        return
    await _edit(call, TEXTS["draw_confirm"].format(title=game.title, count=count), kb.draw_confirm(game.id))
    await call.answer()


@router.callback_query(kb.GameCb.filter(F.action == "draw_ok"))
async def run_draw(call: CallbackQuery, callback_data: kb.GameCb, db: Database, bot: Bot) -> None:
    game = await _own_game(call, db, callback_data.id)
    if game is None:
        return
    count = len(await db.participants(game.id))
    if count < config.MIN_PARTICIPANTS:
        await call.answer(TEXTS["too_few"].format(min=config.MIN_PARTICIPANTS, count=count), show_alert=True)
        return
    try:
        pairs = await db.run_draw(game.id)
    except GameClosed:
        await call.answer(TEXTS["game_closed"], show_alert=True)
        return
    except DrawImpossible as error:
        text = TEXTS["draw_impossible"]
        if error.blocked:
            names = {person.user_id: person.name for person in await db.participants(game.id)}
            blocked = ", ".join(names.get(user_id, "?") for user_id in error.blocked)
            text += "\n\n" + TEXTS["draw_blocked"].format(names=blocked)
        await _edit(call, text, kb.back(game.id))
        await call.answer()
        return
    await call.answer()

    people = {person.user_id: person for person in await db.participants(game.id)}
    header = TEXTS["draw_result"].format(info=game_info(game))
    failed = []
    for giver_id, receiver_id in pairs.items():
        try:
            await bot.send_message(
                giver_id, header + "\n\n" + assignment(people[receiver_id]), reply_markup=kb.chat_buttons(game.id)
            )
        except TelegramAPIError:
            logger.warning("Не удалось отправить результат жеребьёвки %s в игре %s", giver_id, game.id)
            failed.append(people[giver_id].name)
    text = TEXTS["draw_done"]
    if failed:
        text += "\n\n" + TEXTS["draw_undelivered"].format(names=", ".join(failed))
    await _edit(call, text, kb.back(game.id))
