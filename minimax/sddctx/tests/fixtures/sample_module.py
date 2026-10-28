"""A tiny module used by the sddctx unit tests."""


def top_level(value):
    """Return the value unchanged."""
    return value


class Helper:
    """A helper class."""

    def method(self):
        """Return a constant."""
        return 42


def test_one():
    """The first sample test."""
    assert top_level(1) == 1


def test_two():
    """The second sample test."""
    assert Helper().method() == 42
