"""Traffic-light colour used throughout a Wolf run and the consolidated report."""

from __future__ import annotations

from enum import IntEnum


class Colour(IntEnum):
    """Ordered so max(...) picks the worst colour."""

    GREEN = 0
    YELLOW = 1
    RED = 2

    @property
    def emoji(self) -> str:
        return {Colour.GREEN: "🟢", Colour.YELLOW: "🟡", Colour.RED: "🔴"}[self]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


def worst(colours: list[Colour]) -> Colour:
    """The worst (most severe) colour in a list, GREEN if the list is empty."""
    return max(colours, default=Colour.GREEN)
