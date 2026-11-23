"""One place for 'now', so tests can freeze time."""

from __future__ import annotations

from datetime import date, datetime, timezone

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today() -> date:
    return now().date()


def freeze(at: datetime | None) -> None:
    global _frozen
    _frozen = at
