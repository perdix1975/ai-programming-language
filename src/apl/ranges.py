from __future__ import annotations

from typing import Any


I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


def is_range_type(raw: Any) -> bool:
    return (
        isinstance(raw, dict)
        and set(raw) == {"range"}
        and isinstance(raw.get("range"), dict)
        and set(raw["range"]) == {"min", "max"}
    )


def range_bounds(raw: dict[str, Any]) -> tuple[int, int]:
    spec = raw["range"]
    return spec["min"], spec["max"]


def range_contains(raw: dict[str, Any], value: int) -> bool:
    minimum, maximum = range_bounds(raw)
    return minimum <= value <= maximum
