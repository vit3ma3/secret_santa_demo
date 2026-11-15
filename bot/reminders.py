"""Напоминания участникам перед датой обмена подарками.

Раз в час (и сразу при запуске) проверяются разыгранные игры. Начиная
с config.REMINDER_HOUR участникам уходит напоминание, если до обмена осталось
не больше дней, чем очередной порог из config.REMINDER_DAYS. Отправленный порог
хранится в базе, поэтому перезапуск не даёт повторов, а напоминание,
пропущенное, пока бот был выключен, уйдёт при следующей проверке.
"""

import logging
from collections.abc import Iterable
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from bot.db import Database, Game
from bot.views import TEXTS, TZ, assignment, fmt_date, now

logger = logging.getLogger(__name__)


def due_reminder(days_left: int, reminded: int | None, thresholds: Iterable[int]) -> int | None:
    """Порог, по которому пора напомнить, или None.

    Берётся самый близкий к обмену из наступивших порогов: если игру разыграли
    за день до обмена, отдельного напоминания «за 3 дня» не будет.
    """
    reached = [days for days in thresholds if days_left <= days]
    if not reached:
        return None
    due = min(reached)
    if reminded is not None and reminded <= due:
        return None
    return due


class Reminders:
    def __init__(self, bot: Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=TZ)

    def start(self) -> None:
        self.scheduler.add_job(self.check, "cron", minute=0)
        self.scheduler.add_job(self.check)  # без триггера — один раз сразу
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def check(self) -> None:
        current = now()
        if current.hour < config.REMINDER_HOUR:
            return
        for game in await self.db.drawn_games_from(current.date() + timedelta(days=1)):
            days_left = (game.exchange_date - current.date()).days
            due = due_reminder(days_left, game.reminded_days, config.REMINDER_DAYS)
            if due is None:
                continue
            await self.db.set_reminded(game.id, due)
            await self._send(game, days_left)

    async def _send(self, game: Game, days_left: int) -> None:
        participants = {p.user_id: p for p in await self.db.participants(game.id)}
        for participant in participants.values():
            text = TEXTS["reminder"].format(
                title=game.title,
                date=fmt_date(game.exchange_date),
                days=days_left,
                assignment=assignment(participants[participant.receiver_id]),
                budget=game.budget,
            )
            try:
                await self.bot.send_message(participant.user_id, text)
            except TelegramAPIError:
                logger.warning("Не удалось отправить напоминание %s в игре %s", participant.user_id, game.id)
