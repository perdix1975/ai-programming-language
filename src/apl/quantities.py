from __future__ import annotations

import re
from typing import Any


UNIT_SYMBOL_RE = re.compile(r"[a-z][a-z0-9_.-]{0,31}")
MAX_UNIT_TERMS = 16
MAX_UNIT_EXPONENT = 16


def is_quantity_type(raw: Any) -> bool:
    return (
        isinstance(raw, dict)
        and set(raw) == {"quantity"}
        and isinstance(raw.get("quantity"), dict)
    )


def combine_quantity_types(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    divide: bool,
) -> dict[str, Any]:
    units = dict(left["quantity"])
    sign = -1 if divide else 1
    for symbol, exponent in right["quantity"].items():
        combined = units.get(symbol, 0) + sign * exponent
        if combined == 0:
            units.pop(symbol, None)
        else:
            if abs(combined) > MAX_UNIT_EXPONENT:
                raise ValueError(
                    f"derived exponent for unit '{symbol}' exceeds "
                    f"[-{MAX_UNIT_EXPONENT}, {MAX_UNIT_EXPONENT}]"
                )
            units[symbol] = combined
    if len(units) > MAX_UNIT_TERMS:
        raise ValueError(
            f"derived quantity contains more than {MAX_UNIT_TERMS} unit terms"
        )
    return {"quantity": dict(sorted(units.items()))}
