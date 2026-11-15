"""Игры, участники и исключения в SQLite.

Изменения состава игры и жеребьёвка выполняются под общим замком,
чтобы никто не вступил в игру, пока считаются пары.
"""

import asyncio
import secrets
from dataclasses import dataclass
from datetime import date

import aiosqlite

from bot.draw import draw

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT    NOT NULL UNIQUE,
    title         TEXT    NOT NULL,
    budget        TEXT    NOT NULL,
    exchange_date TEXT    NOT NULL,
    organizer_id  INTEGER NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'open',
    reminded_days INTEGER,
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_games_organizer ON games (organizer_id);

CREATE TABLE IF NOT EXISTS participants (
    game_id     INTEGER NOT NULL REFERENCES games (id),
    user_id     INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    wishes      TEXT    NOT NULL,
    receiver_id INTEGER,
    joined_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_participants_user ON participants (user_id);

CREATE TABLE IF NOT EXISTS exclusions (
    game_id INTEGER NOT NULL REFERENCES games (id),
    user_a  INTEGER NOT NULL,
    user_b  INTEGER NOT NULL,
    PRIMARY KEY (game_id, user_a, user_b)
);
"""

OPEN = "open"
DRAWN = "drawn"


@dataclass(frozen=True)
class Game:
    id: int
    code: str
    title: str
    budget: str
    exchange_date: date
    organizer_id: int
    status: str
    reminded_days: int | None  # последний отправленный порог напоминания

    @property
    def is_open(self) -> bool:
        return self.status == OPEN

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Game":
        return cls(
            id=row["id"],
            code=row["code"],
            title=row["title"],
            budget=row["budget"],
            exchange_date=date.fromisoformat(row["exchange_date"]),
            organizer_id=row["organizer_id"],
            status=row["status"],
            reminded_days=row["reminded_days"],
        )


@dataclass(frozen=True)
class Participant:
    game_id: int
    user_id: int
    name: str
    wishes: str
    receiver_id: int | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Participant":
        return cls(
            game_id=row["game_id"],
            user_id=row["user_id"],
            name=row["name"],
            wishes=row["wishes"],
            receiver_id=row["receiver_id"],
        )


class GameClosed(Exception):
    """Жеребьёвка уже проведена (или игры нет): состав менять нельзя."""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() не вызван"
        return self._conn

    # --- Игры ----------------------------------------------------------------

    async def create_game(self, organizer_id: int, title: str, budget: str, exchange_date: date) -> Game:
        cursor = await self.conn.execute(
            "INSERT INTO games (code, title, budget, exchange_date, organizer_id) VALUES (?, ?, ?, ?, ?)",
            (secrets.token_urlsafe(8), title, budget, exchange_date.isoformat(), organizer_id),
        )
        await self.conn.commit()
        game = await self.get_game(cursor.lastrowid)
        assert game is not None
        return game

    async def get_game(self, game_id: int) -> Game | None:
        cursor = await self.conn.execute("SELECT * FROM games WHERE id = ?", (game_id,))
        row = await cursor.fetchone()
        return Game.from_row(row) if row else None

    async def get_game_by_code(self, code: str) -> Game | None:
        cursor = await self.conn.execute("SELECT * FROM games WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return Game.from_row(row) if row else None

    async def organizer_games(self, user_id: int) -> list[Game]:
        cursor = await self.conn.execute(
            "SELECT * FROM games WHERE organizer_id = ? ORDER BY exchange_date, id", (user_id,)
        )
        return [Game.from_row(row) for row in await cursor.fetchall()]

    async def participant_games(self, user_id: int) -> list[Game]:
        cursor = await self.conn.execute(
            "SELECT g.* FROM games g JOIN participants p ON p.game_id = g.id"
            " WHERE p.user_id = ? ORDER BY g.exchange_date, g.id",
            (user_id,),
        )
        return [Game.from_row(row) for row in await cursor.fetchall()]

    # --- Участники -----------------------------------------------------------

    async def participants(self, game_id: int) -> list[Participant]:
        cursor = await self.conn.execute(
            "SELECT * FROM participants WHERE game_id = ? ORDER BY joined_at, rowid", (game_id,)
        )
        return [Participant.from_row(row) for row in await cursor.fetchall()]

    async def get_participant(self, game_id: int, user_id: int) -> Participant | None:
        cursor = await self.conn.execute(
            "SELECT * FROM participants WHERE game_id = ? AND user_id = ?", (game_id, user_id)
        )
        row = await cursor.fetchone()
        return Participant.from_row(row) if row else None

    async def santa_of(self, game_id: int, user_id: int) -> Participant | None:
        cursor = await self.conn.execute(
            "SELECT * FROM participants WHERE game_id = ? AND receiver_id = ?", (game_id, user_id)
        )
        row = await cursor.fetchone()
        return Participant.from_row(row) if row else None

    async def add_participant(self, game_id: int, user_id: int, name: str, wishes: str) -> None:
        async with self._lock:
            await self._ensure_open(game_id)
            await self.conn.execute(
                "INSERT OR IGNORE INTO participants (game_id, user_id, name, wishes) VALUES (?, ?, ?, ?)",
                (game_id, user_id, name, wishes),
            )
            await self.conn.commit()

    async def update_participant(self, game_id: int, user_id: int, field: str, value: str) -> None:
        assert field in ("name", "wishes")
        await self.conn.execute(
            f"UPDATE participants SET {field} = ? WHERE game_id = ? AND user_id = ?",
            (value, game_id, user_id),
        )
        await self.conn.commit()

    async def remove_participant(self, game_id: int, user_id: int) -> None:
        async with self._lock:
            await self._ensure_open(game_id)
            await self.conn.execute(
                "DELETE FROM participants WHERE game_id = ? AND user_id = ?", (game_id, user_id)
            )
            await self.conn.execute(
                "DELETE FROM exclusions WHERE game_id = ? AND (user_a = ? OR user_b = ?)",
                (game_id, user_id, user_id),
            )
            await self.conn.commit()

    # --- Исключения ----------------------------------------------------------

    async def exclusions(self, game_id: int) -> list[tuple[int, int]]:
        cursor = await self.conn.execute(
            "SELECT user_a, user_b FROM exclusions WHERE game_id = ? ORDER BY rowid", (game_id,)
        )
        return [(a, b) for a, b in await cursor.fetchall()]

    async def add_exclusion(self, game_id: int, a: int, b: int) -> None:
        async with self._lock:
            await self._ensure_open(game_id)
            await self.conn.execute(
                "INSERT OR IGNORE INTO exclusions (game_id, user_a, user_b) VALUES (?, ?, ?)",
                (game_id, min(a, b), max(a, b)),
            )
            await self.conn.commit()

    async def delete_exclusion(self, game_id: int, a: int, b: int) -> None:
        async with self._lock:
            await self._ensure_open(game_id)
            await self.conn.execute(
                "DELETE FROM exclusions WHERE game_id = ? AND user_a = ? AND user_b = ?",
                (game_id, min(a, b), max(a, b)),
            )
            await self.conn.commit()

    # --- Жеребьёвка ----------------------------------------------------------

    async def run_draw(self, game_id: int) -> dict[int, int]:
        """Разыгрывает пары и закрывает игру.

        Бросает GameClosed, если жеребьёвка уже была, и DrawImpossible,
        если исключения не дают составить пары.
        """
        async with self._lock:
            await self._ensure_open(game_id)
            people = [p.user_id for p in await self.participants(game_id)]
            pairs = draw(people, await self.exclusions(game_id))
            await self.conn.executemany(
                "UPDATE participants SET receiver_id = ? WHERE game_id = ? AND user_id = ?",
                [(receiver, game_id, giver) for giver, receiver in pairs.items()],
            )
            await self.conn.execute("UPDATE games SET status = ? WHERE id = ?", (DRAWN, game_id))
            await self.conn.commit()
        return pairs

    async def _ensure_open(self, game_id: int) -> None:
        game = await self.get_game(game_id)
        if game is None or not game.is_open:
            raise GameClosed

    # --- Напоминания ---------------------------------------------------------

    async def drawn_games_from(self, day: date) -> list[Game]:
        cursor = await self.conn.execute(
            "SELECT * FROM games WHERE status = ? AND exchange_date >= ?", (DRAWN, day.isoformat())
        )
        return [Game.from_row(row) for row in await cursor.fetchall()]

    async def set_reminded(self, game_id: int, days: int) -> None:
        await self.conn.execute("UPDATE games SET reminded_days = ? WHERE id = ?", (days, game_id))
        await self.conn.commit()
