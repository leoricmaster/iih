"""parse_duration_to_seconds 单测（IIH-03.01）。"""

from iih.ledger.duration import parse_duration_to_seconds


def test_parse_hours() -> None:
    assert parse_duration_to_seconds("1h") == 3600
    assert parse_duration_to_seconds("24h") == 86400
    assert parse_duration_to_seconds("6h") == 21600


def test_parse_days_and_weeks() -> None:
    assert parse_duration_to_seconds("7d") == 604800
    assert parse_duration_to_seconds("1w") == 604800
    assert parse_duration_to_seconds("30m") == 1800


def test_parse_minutes_and_seconds() -> None:
    assert parse_duration_to_seconds("90s") == 90


def test_parse_case_insensitive() -> None:
    assert parse_duration_to_seconds("1H") == 3600
    assert parse_duration_to_seconds("7D") == 604800


def test_parse_whitespace_tolerant() -> None:
    assert parse_duration_to_seconds("  1h  ") == 3600


def test_parse_empty_or_none_returns_none() -> None:
    assert parse_duration_to_seconds(None) is None
    assert parse_duration_to_seconds("") is None
    assert parse_duration_to_seconds("   ") is None


def test_parse_invalid_returns_none() -> None:
    assert parse_duration_to_seconds("一周内") is None
    assert parse_duration_to_seconds("1 hour") is None
    assert parse_duration_to_seconds("abc") is None
    assert parse_duration_to_seconds("1") is None
    assert parse_duration_to_seconds("h") is None
    assert parse_duration_to_seconds("1.5h") is None
