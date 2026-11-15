"""Анонимная переписка через бота: с подопечным и со своим Сантой.

Сообщение копируется (copy_message), а не пересылается, поэтому
получатель не видит, кто его отправил.
"""

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.db import Database
from bot.handlers.participant import membership
from bot.states import ChatFlow
from bot.views import TEXTS

router = Router()


@router.callback_query(kb.ChatCb.filter())
async def start_chat(call: CallbackQuery, callback_data: kb.ChatCb, state: FSMContext, db: Database) -> None:
    found = await membership(call, db, callback_data.game_id)
    if found is None:
        return
    game, _ = found
    if game.is_open:
        await call.answer(TEXTS["chat_not_ready"], show_alert=True)
        return
    await state.set_state(ChatFlow.message)
    await state.update_data(game_id=game.id, to=callback_data.to)
    await call.message.answer(TEXTS[f"ask_message_{callback_data.to}"], reply_markup=kb.cancel())
    await call.answer()


@router.message(ChatFlow.message, kb.NOT_MENU)
async def send(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    game = await db.get_game(data["game_id"])
    me = await db.get_participant(data["game_id"], message.from_user.id)
    if game is None or me is None:
        await message.answer(TEXTS["stale_button"], reply_markup=kb.main_menu())
        return

    if data["to"] == kb.TO_RECEIVER:
        target_id = me.receiver_id
        header, reply_to = TEXTS["msg_from_santa"], kb.TO_SANTA
    else:
        santa = await db.santa_of(game.id, me.user_id)
        target_id = santa.user_id if santa else None
        header, reply_to = TEXTS["msg_from_receiver"], kb.TO_RECEIVER
    if target_id is None:
        await message.answer(TEXTS["stale_button"], reply_markup=kb.main_menu())
        return

    try:
        await bot.send_message(target_id, header.format(title=game.title))
        await message.copy_to(target_id, reply_markup=kb.reply(game.id, reply_to))
    except TelegramForbiddenError:
        await message.answer(TEXTS["chat_undelivered"], reply_markup=kb.main_menu())
        return
    except TelegramBadRequest:
        await message.answer(TEXTS["chat_unsupported"], reply_markup=kb.main_menu())
        return
    await message.answer(TEXTS["chat_sent"], reply_markup=kb.main_menu())
