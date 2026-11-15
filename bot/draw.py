"""Жеребьёвка: кто кому дарит подарок.

Задача сводится к поиску совершенного паросочетания в двудольном графе
«даритель → получатель», где запрещены рёбра «сам себе» и пары-исключения.
Используется алгоритм Куна: он за полиномиальное время либо находит пары,
либо доказывает, что их нет. Случайность даёт перемешивание порядка перебора.
"""

import random
from collections.abc import Hashable, Iterable, Sequence


class DrawImpossible(Exception):
    """Исключения не позволяют составить пары."""

    def __init__(self, blocked: list[Hashable]) -> None:
        super().__init__("Жеребьёвка невозможна")
        # Участники, которым по исключениям некого дарить (может быть пусто,
        # если невозможность складывается из нескольких исключений сразу).
        self.blocked = blocked


def draw(
    participants: Sequence[Hashable],
    exclusions: Iterable[tuple[Hashable, Hashable]] = (),
    rng: random.Random | None = None,
) -> dict[Hashable, Hashable]:
    """Возвращает словарь {даритель: получатель}.

    Исключения симметричны: пара (a, b) запрещает и a → b, и b → a.
    """
    rng = rng or random.Random()
    people = list(participants)
    forbidden = {frozenset(pair) for pair in exclusions}
    allowed = {
        giver: [r for r in people if r != giver and frozenset((giver, r)) not in forbidden]
        for giver in people
    }
    blocked = [giver for giver, options in allowed.items() if not options]
    if len(people) < 2 or blocked:
        raise DrawImpossible(blocked)

    for options in allowed.values():
        rng.shuffle(options)
    givers = people[:]
    rng.shuffle(givers)

    giver_of: dict[Hashable, Hashable] = {}  # получатель -> даритель

    def assign(giver: Hashable, seen: set[Hashable]) -> bool:
        for receiver in allowed[giver]:
            if receiver in seen:
                continue
            seen.add(receiver)
            if receiver not in giver_of or assign(giver_of[receiver], seen):
                giver_of[receiver] = giver
                return True
        return False

    for giver in givers:
        if not assign(giver, set()):
            raise DrawImpossible([])
    return {giver: receiver for receiver, giver in giver_of.items()}
