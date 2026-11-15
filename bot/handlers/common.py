"""/start (в том числе по ссылке-приглашению), справка и выход из любого сценария."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import keyboards as kb
from bot.db import Database
from bot.handlers import participant
from bot.views import JOIN_PREFIX, TEXTS

router = Router()
# Подключается последним: отвечает на то, что не подошло ни одному обработчику.
fallback_router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, command: CommandObject, db: Database) -> None:
    await state.clear()
    if command.args and command.args.startswith(JOIN_PREFIX):
        await participant.begin_join(message, state, db, command.args.removeprefix(JOIN_PREFIX))
        return
    text = TEXTS["welcome"]
    if config.IS_DEMO:
        text += "\n\n" + TEXTS["demo_note"]
    await message.answer(text, reply_markup=kb.main_menu())


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer(TEXTS["help"], reply_markup=kb.main_menu())


@router.callback_query(F.data == kb.CANCEL_FLOW)
async def cancel_flow(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.message.answer(TEXTS["flow_cancelled"], reply_markup=kb.main_menu())
    await call.answer()


@fallback_router.callback_query()
async def stale_button(call: CallbackQuery) -> None:
    await call.answer(TEXTS["stale_button"], show_alert=True)


@fallback_router.message()
async def unknown(message: Message) -> None:
    await message.answer(TEXTS["unknown"], reply_markup=kb.main_menu())
