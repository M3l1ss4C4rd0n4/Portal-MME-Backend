"""Tests básicos para shared.utils.date_utils"""

from datetime import date
from shared.utils.date_utils import format_date, parse_date, days_between, date_range


def test_format_and_parse_date():
    d = date(2026, 1, 28)
    assert format_date(d) == "2026-01-28"
    assert parse_date("2026-01-28") == d


def test_days_between():
    assert days_between("2026-01-01", "2026-01-10") == 9


def test_date_range():
    dates = date_range("2026-01-01", "2026-01-03")
    assert len(dates) == 3
