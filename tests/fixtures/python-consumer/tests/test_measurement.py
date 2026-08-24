"""Tests for the disposable package."""

from package import normalized_total

EXPECTED_TOTAL = 5


def test_normalized_total() -> None:
    """The calculation retains every supplied sample."""
    assert normalized_total([2, 3]) == EXPECTED_TOTAL
