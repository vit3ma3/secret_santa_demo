"""Точка входа: python -m bot"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from bot.db import Database
from bot.handlers import chat, common, organizer, participant
from bot.reminders import Reminders
from bot.settings import settings
from bot.views import TEXTS


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db = Database(settings.db_path)
    await db.connect()
    bot = Bot(settings.bot_token)
    reminders = Reminders(bot, db)
    reminders.start()

    dp = Dispatcher()
    # Шаги сценариев отфильтрованы от кнопок меню и команд,
    # а fallback подключается последним.
    dp.include_routers(
        common.router,
        organizer.router,
        participant.router,
        chat.router,
        common.fallback_router,
    )

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description=TEXTS["cmd_start"]),
                BotCommand(command="help", description=TEXTS["cmd_help"]),
            ]
        )
        await dp.start_polling(bot, db=db)
    finally:
        reminders.shutdown()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
