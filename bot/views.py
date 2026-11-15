"""Часовой пояс, даты, ссылки-приглашения и тексты карточек."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.utils.deep_linking import create_start_link

import config
from bot.db import Game, Participant

TZ = ZoneInfo(config.TIMEZONE)
TEXTS = config.TEXTS
JOIN_PREFIX = "join_"


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def fmt_date(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def clean_text(text: str, max_len: int) -> str | None:
    """Ввод пользователя без лишних пробелов или None, если он пустой или длинный."""
    text = text.strip()
    return text if 0 < len(text) <= max_len else None


async def invite_link(bot: Bot, game: Game) -> str:
    return await create_start_link(bot, JOIN_PREFIX + game.code)


def game_info(game: Game) -> str:
    return TEXTS["game_info"].format(title=game.title, budget=game.budget, date=fmt_date(game.exchange_date))


def assignment(receiver: Participant) -> str:
    return TEXTS["assignment"].format(name=receiver.name, wishes=receiver.wishes)


async def organizer_card(bot: Bot, game: Game, count: int) -> str:
    text = game_info(game) + "\n" + TEXTS["card_members"].format(count=count) + "\n\n"
    if game.is_open:
        return text + TEXTS["card_open"].format(link=await invite_link(bot, game))
    return text + TEXTS["card_drawn"]


def participant_card(game: Game, me: Participant, receiver: Participant | None) -> str:
    text = game_info(game) + "\n\n" + TEXTS["card_me"].format(name=me.name, wishes=me.wishes) + "\n\n"
    return text + (assignment(receiver) if receiver else TEXTS["card_waiting"])
