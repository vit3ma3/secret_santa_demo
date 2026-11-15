import random
from itertools import permutations

import pytest

from bot.draw import DrawImpossible, draw


def assert_valid(pairs: dict, people: list, exclusions=()) -> None:
    assert set(pairs) == set(people), "каждый должен дарить"
    assert sorted(pairs.values()) == sorted(people), "каждый должен получить ровно один подарок"
    forbidden = {frozenset(pair) for pair in exclusions}
    for giver, receiver in pairs.items():
        assert giver != receiver, "никто не дарит себе"
        assert frozenset((giver, receiver)) not in forbidden, "исключения соблюдаются"


def brute_force_possible(people: list, exclusions) -> bool:
    forbidden = {frozenset(pair) for pair in exclusions}
    return any(
        all(g != r and frozenset((g, r)) not in forbidden for g, r in zip(people, perm))
        for perm in permutations(people)
    )


@pytest.mark.parametrize("size", [2, 3, 4, 5, 10, 50])
def test_nobody_gifts_themselves_and_everyone_gets_one_gift(size):
    people = list(range(size))
    for seed in range(50):
        assert_valid(draw(people, rng=random.Random(seed)), people)


def test_two_people_gift_each_other():
    assert draw(["a", "b"]) == {"a": "b", "b": "a"}


def test_exclusions_are_respected_in_both_directions():
    people = ["Аня", "Боря", "Вика", "Гена", "Даша"]
    exclusions = [("Аня", "Боря"), ("Вика", "Гена")]
    for seed in range(200):
        assert_valid(draw(people, exclusions, rng=random.Random(seed)), people, exclusions)


def test_couples_only_have_one_valid_draw_pattern():
    # Две пары: каждый может дарить только кому-то из другой пары.
    people = ["a1", "a2", "b1", "b2"]
    exclusions = [("a1", "a2"), ("b1", "b2")]
    for seed in range(50):
        pairs = draw(people, exclusions, rng=random.Random(seed))
        assert_valid(pairs, people, exclusions)


def test_impossible_when_two_people_can_only_gift_the_same_person():
    # Аня и Боря исключены друг для друга: обоим остаётся только Вика.
    with pytest.raises(DrawImpossible) as error:
        draw(["Аня", "Боря", "Вика"], [("Аня", "Боря")])
    assert error.value.blocked == []


def test_impossible_reports_who_has_nobody_to_gift():
    people = ["Аня", "Боря", "Вика", "Гена"]
    exclusions = [("Аня", "Боря"), ("Аня", "Вика"), ("Аня", "Гена")]
    with pytest.raises(DrawImpossible) as error:
        draw(people, exclusions)
    assert error.value.blocked == ["Аня"]


@pytest.mark.parametrize("people", [[], ["solo"]])
def test_impossible_with_fewer_than_two_people(people):
    with pytest.raises(DrawImpossible):
        draw(people)


def test_matches_brute_force_on_random_small_games():
    """Жеребьёвка находит пары ровно тогда, когда они существуют."""
    rng = random.Random(42)
    for _ in range(300):
        people = list(range(rng.randint(2, 6)))
        all_pairs = [(a, b) for a in people for b in people if a < b]
        exclusions = rng.sample(all_pairs, rng.randint(0, len(all_pairs)))
        if brute_force_possible(people, exclusions):
            assert_valid(draw(people, exclusions, rng=rng), people, exclusions)
        else:
            with pytest.raises(DrawImpossible):
                draw(people, exclusions, rng=rng)


def test_result_is_random():
    people = list(range(6))
    results = {tuple(sorted(draw(people).items())) for _ in range(200)}
    assert len(results) > 20


def test_same_seed_gives_same_result():
    people = list(range(10))
    assert draw(people, rng=random.Random(7)) == draw(people, rng=random.Random(7))


def test_large_game_with_many_exclusions():
    rng = random.Random(1)
    people = list(range(200))
    exclusions = [(a, b) for a in people for b in people if a < b and rng.random() < 0.3]
    assert_valid(draw(people, exclusions, rng=rng), people, exclusions)
