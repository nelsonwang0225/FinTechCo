from __future__ import annotations

import pytest

from app.core import money


def test_fee_is_integer_half_up_plus_fixed_part() -> None:
    assert money.fee_cents(24800, "website") == 749  # 2.9% of 248.00 = 7.192 -> 7.19 + 0.30
    assert money.fee_cents(950, "in_store") == 31  # 2.7% of 9.50 = 0.2565 -> 0.26 + 0.05
    assert money.fee_cents(1, "mobile_app") == 30
    with pytest.raises(ValueError):
        money.fee_cents(0, "website")


def test_format_usd_handles_negatives_and_thousands() -> None:
    assert money.format_usd(-4850) == "-48.50"
    assert money.format_usd(5) == "0.05"
    assert money.format_usd(123456789, symbol=True) == "$1,234,567.89"
    assert money.format_usd(-100, symbol=True) == "-$1.00"


def test_parse_usd_is_integer_only() -> None:
    assert money.parse_usd("1,234.5") == 123450
    assert money.parse_usd("$12") == 1200
    assert money.parse_usd("-3.07") == -307
    assert money.parse_usd(".5") == 50
    with pytest.raises(ValueError):
        money.parse_usd("1.234")
    with pytest.raises(ValueError):
        money.parse_usd("abc")
