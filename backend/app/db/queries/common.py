"""Helpers shared by the query modules."""

from __future__ import annotations

from dataclasses import dataclass


def escape_like(text: str) -> str:
    r"""Escape LIKE wildcards in user input; pair with ESCAPE '\'."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class Page:
    page: int = 1
    page_size: int = 25

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def order_clause(sort_columns: dict[str, str], sort: str, direction: str, tiebreaker: str) -> str:
    """ORDER BY from a whitelist; never from a user string."""
    column = sort_columns[sort]
    direction_sql = "DESC" if direction == "desc" else "ASC"
    return f"ORDER BY {column} {direction_sql}, {tiebreaker} {direction_sql}"
