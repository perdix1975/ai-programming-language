from __future__ import annotations

from copy import deepcopy
from typing import Any

from .lir import lower_program, verify_lir


I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


def _trunc_div(a: int, b: int) -> int | None:
    if b == 0 or (a == I64_MIN and b == -1):
        return None
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _trunc_rem(a: int, b: int) -> int | None:
    if b == 0:
        return None
    if a == I64_MIN and b == -1:
        return 0
    q = _trunc_div(a, b)
    if q is None:
        return None
    return a - q * b


def _checked_i64(value: int) -> int | None:
    return value if I64_MIN <= value <= I64_MAX else None


def _const_op(op: dict[str, Any], value: Any) -> dict[str, Any]:
    return {
        "op": "const",
        "id": op["id"],
        "type": op["type"],
        "value": value,
    }


def _fold_value_op(
    op: dict[str, Any],
    constants: dict[str, tuple[Any, Any]],
) -> dict[str, Any] | None:
    name = op["op"]
    args = op.get("args")
    if not isinstance(args, list) or any(arg not in constants for arg in args):
        return None

    values = [constants[arg][1] for arg in args]
    types = [constants[arg][0] for arg in args]

    value: Any | None = None
    folded = True

    if name == "i64.add":
        value = _checked_i64(values[0] + values[1])
        folded = value is not None
    elif name == "i64.sub":
        value = _checked_i64(values[0] - values[1])
        folded = value is not None
    elif name == "i64.mul":
        value = _checked_i64(values[0] * values[1])
        folded = value is not None
    elif name == "i64.div":
        value = _trunc_div(values[0], values[1])
        folded = value is not None
    elif name == "i64.rem":
        value = _trunc_rem(values[0], values[1])
        folded = value is not None
    elif name == "i64.lt":
        value = values[0] < values[1]
    elif name == "i64.le":
        value = values[0] <= values[1]
    elif name == "i64.gt":
        value = values[0] > values[1]
    elif name == "i64.ge":
        value = values[0] >= values[1]
    elif name == "value.eq" and types[0] == types[1] and types[0] in {
        "i64",
        "bool",
        "string",
    }:
        value = values[0] == values[1]
    elif name == "bool.not":
        value = not values[0]
    elif name == "bool.and":
        value = bool(values[0] and values[1])
    elif name == "bool.or":
        value = bool(values[0] or values[1])
    else:
        folded = False

    if not folded:
        return None
    return _const_op(op, value)


def _optimize_function(fn: dict[str, Any]) -> None:
    for block in fn["blocks"]:
        constants: dict[str, tuple[Any, Any]] = {}

        for index, op in enumerate(block["ops"]):
            name = op["op"]

            if name == "const":
                constants[op["id"]] = (op["type"], op["value"])
                continue

            if name == "array.len":
                source = op["arg"]
                source_type = None
                for param in fn["params"]:
                    if param["id"] == source:
                        source_type = param["type"]
                        break
                if source_type is None:
                    for candidate_block in fn["blocks"]:
                        for param in candidate_block["params"]:
                            if param["id"] == source:
                                source_type = param["type"]
                                break
                        if source_type is not None:
                            break
                        for candidate in candidate_block["ops"]:
                            if candidate.get("id") == source:
                                source_type = candidate.get("type")
                                break
                        if source_type is not None:
                            break
                if (
                    isinstance(source_type, dict)
                    and set(source_type) == {"array", "len"}
                ):
                    folded = _const_op(op, source_type["len"])
                    block["ops"][index] = folded
                    constants[op["id"]] = ("i64", source_type["len"])
                    continue

            folded = _fold_value_op(op, constants)
            if folded is not None:
                block["ops"][index] = folded
                constants[op["id"]] = (folded["type"], folded["value"])
            elif "id" in op:
                constants.pop(op["id"], None)

        term = block["term"]
        if term["op"] == "cond_br":
            cond = term["cond"]
            const = constants.get(cond)
            if const is not None and const[0] == "bool":
                selected = term["then"] if const[1] else term["else"]
                block["term"] = {
                    "op": "br",
                    "target": selected["target"],
                    "args": list(selected["args"]),
                }


def optimize_lir(lir: dict[str, Any]) -> dict[str, Any]:
    """Deterministically apply semantics-preserving LIR optimizations."""
    verify_lir(lir)
    optimized = deepcopy(lir)
    for fn in optimized["functions"]:
        _optimize_function(fn)
    verify_lir(optimized)
    return optimized


def optimize_program(program: dict[str, Any]) -> dict[str, Any]:
    return optimize_lir(lower_program(program))
