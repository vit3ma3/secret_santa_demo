from bot.reminders import due_reminder

THRESHOLDS = [3, 1]


def test_no_reminder_while_exchange_is_far():
    assert due_reminder(10, None, THRESHOLDS) is None
    assert due_reminder(4, None, THRESHOLDS) is None


def test_three_days_then_one_day():
    assert due_reminder(3, None, THRESHOLDS) == 3
    assert due_reminder(2, 3, THRESHOLDS) is None
    assert due_reminder(1, 3, THRESHOLDS) == 1
    assert due_reminder(1, 1, THRESHOLDS) is None


def test_missed_reminder_is_sent_later():
    # Бот был выключен в день «за 3 дня» — напомним на следующий день.
    assert due_reminder(2, None, THRESHOLDS) == 3


def test_late_draw_gets_only_the_closest_reminder():
    # Игру разыграли за день до обмена — «за 3 дня» отдельно не шлём.
    assert due_reminder(1, None, THRESHOLDS) == 1
