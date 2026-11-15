"""Секреты и параметры окружения из .env."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str


def _load() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Заполните BOT_TOKEN в файле .env (образец — .env.example)")
    return Settings(bot_token=token, db_path=os.getenv("DB_PATH", "santa.db"))


settings = _load()
