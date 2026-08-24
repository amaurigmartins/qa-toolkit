"""Small deterministic calculations for the disposable target."""


def normalized_total(values: list[int]) -> int:
    """Return the sum of the supplied integer samples.

    Args:
        values (list[int]): Integer samples to add.

    Returns:
        int: The sum of all samples.
    """
    return sum(values)
