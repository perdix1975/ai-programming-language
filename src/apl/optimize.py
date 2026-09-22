from __future__ import annotations

from copy import deepcopy
from typing import Any

from .lir import verify_lir


I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


def _checked_i64(value: int) -> int | None:
    if I64_MIN <= value <= I64_MAX:
        return value
    return None


def _trunc_div(a: int, b: int) -> int | None:
    if b == 0:
        return None
    if a == I64_MIN and b == -1:
        return None
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def _trunc_rem(a: int, b: int) -> int | None:
    if b == 0:
        return None
    if a == I64_MIN and b == -1:
        return 0
    quotient = _trunc_div(a, b)
    if quotient is None:
        return None
    return a - quotient * b


def _const_op(value_id: str, typ: Any, value: Any) -> dict[str, Any]:
    return {
        "op": "const",
        "id": value_id,
        "type": typ,
        "value": value,
    }


def _build_value_types(fn: dict[str, Any]) -> dict[str, Any]:
    types = {
        param["id"]: param["type"]
        for param in fn["params"]
    }
    for block in fn["blocks"]:
        for param in block["params"]:
            types[param["id"]] = param["type"]
        for op in block["ops"]:
            if "id" in op:
                types[op["id"]] = op["type"]
    return types


def _fold_op(
    op: dict[str, Any],
    constants: dict[str, tuple[Any, Any]],
    value_types: dict[str, Any],
) -> dict[str, Any] | None:
    name = op["op"]
    value_id = op.get("id")
    if value_id is None:
        return None

    if name == "const":
        return None

    if name == "array.len":
        source_type = value_types[op["arg"]]
        if (
            isinstance(source_type, dict)
            and set(source_type) == {"array", "len"}
        ):
            return _const_op(value_id, "i64", source_type["len"])
        return None

    args = op.get("args")
    if not isinstance(args, list):
        return None
    if any(arg not in constants for arg in args):
        return None

    values = [constants[arg][1] for arg in args]
    types = [constants[arg][0] for arg in args]

    if name in {"i64.add", "i64.sub", "i64.mul"}:
        a, b = values
        raw = (
            a + b
            if name == "i64.add"
            else a - b
            if name == "i64.sub"
            else a * b
        )
        folded = _checked_i64(raw)
        if folded is None:
            return None
        return _const_op(value_id, "i64", folded)

    if name == "i64.div":
        folded = _trunc_div(values[0], values[1])
        if folded is None:
            return None
        return _const_op(value_id, "i64", folded)

    if name == "i64.rem":
        folded = _trunc_rem(values[0], values[1])
        if folded is None:
            return None
        return _const_op(value_id, "i64", folded)

    if name in {"i64.lt", "i64.le", "i64.gt", "i64.ge"}:
        a, b = values
        result = (
            a < b
            if name == "i64.lt"
            else a <= b
            if name == "i64.le"
            else a > b
            if name == "i64.gt"
            else a >= b
        )
        return _const_op(value_id, "bool", result)

    if name == "value.eq":
        if types[0] == types[1] and types[0] in {"i64", "bool", "string"}:
            return _const_op(value_id, "bool", values[0] == values[1])
        return None

    if name in {"value.lt", "value.le", "value.gt", "value.ge"}:
        if types[0] != "i64" or types[1] != "i64":
            return None
        a, b = values
        result = (
            a < b
            if name == "value.lt"
            else a <= b
            if name == "value.le"
            else a > b
            if name == "value.gt"
            else a >= b
        )
        return _const_op(value_id, "bool", result)

    if name == "bool.not":
        return _const_op(value_id, "bool", not values[0])

    if name == "bool.and":
        return _const_op(value_id, "bool", bool(values[0] and values[1]))

    if name == "bool.or":
        return _const_op(value_id, "bool", bool(values[0] or values[1]))

    return None


def optimize_lir(lir: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic trap-preserving local optimizations to verified LIR."""
    verify_lir(lir)
    optimized = deepcopy(lir)

    for fn in optimized["functions"]:
        value_types = _build_value_types(fn)

        for block in fn["blocks"]:
            constants: dict[str, tuple[Any, Any]] = {}
            new_ops: list[dict[str, Any]] = []

            # Block parameters are intentionally not propagated as constants
            # across CFG edges in optimizer 0.1.
            for op in block["ops"]:
                folded = _fold_op(op, constants, value_types)
                selected = folded if folded is not None else op
                new_ops.append(selected)

                value_id = selected.get("id")
                if value_id is not None:
                    if selected["op"] == "const":
                        constants[value_id] = (
                            selected["type"],
                            selected["value"],
                        )
                    else:
                        constants.pop(value_id, None)

            block["ops"] = new_ops

    verify_lir(optimized)
    return optimized
