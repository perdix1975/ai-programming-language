from __future__ import annotations

import re
from typing import Any

from .errors import ExecutionError, VerificationError
from .ranges import is_range_type
from .resources import ExecutionBudget


CONTRACT_ID_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
MAX_CONTRACTS_PER_KIND = 64
MAX_CONTRACT_MESSAGE_LENGTH = 512
MAX_PREDICATE_DEPTH = 64
MAX_PREDICATE_NODES = 1024
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _const_type(raw: Any, where: str) -> str:
    _expect(
        isinstance(raw, dict) and set(raw) == {"type", "value"},
        f"{where}: const must contain exactly 'type' and 'value'",
    )
    typ = raw.get("type")
    value = raw.get("value")
    _expect(typ in {"i64", "bool", "string"}, f"{where}: invalid const type '{typ}'")
    valid = (
        (
            typ == "i64"
            and isinstance(value, int)
            and not isinstance(value, bool)
            and I64_MIN <= value <= I64_MAX
        )
        or (typ == "bool" and isinstance(value, bool))
        or (typ == "string" and isinstance(value, str))
    )
    _expect(valid, f"{where}: constant value does not match type '{typ}'")
    return typ


def _predicate_type(
    expr: Any,
    *,
    env_types: dict[str, Any],
    result_type: Any,
    allow_result: bool,
    where: str,
    depth: int,
    nodes: list[int],
) -> Any:
    _expect(isinstance(expr, dict), f"{where}: predicate node must be an object")
    _expect(depth <= MAX_PREDICATE_DEPTH, f"{where}: predicate depth exceeds {MAX_PREDICATE_DEPTH}")
    nodes[0] += 1
    _expect(
        nodes[0] <= MAX_PREDICATE_NODES,
        f"{where}: predicate contains more than {MAX_PREDICATE_NODES} nodes",
    )

    if set(expr) == {"var"}:
        name = expr.get("var")
        _expect(isinstance(name, str) and name in env_types, f"{where}: unknown contract variable '{name}'")
        return env_types[name]

    if set(expr) == {"result"}:
        _expect(expr.get("result") is True, f"{where}: result reference must be true")
        _expect(allow_result, f"{where}: function result is not available in this contract")
        _expect(result_type != "unit", f"{where}: unit function has no result value")
        return result_type

    if set(expr) == {"const"}:
        return _const_type(expr["const"], f"{where}.const")

    _expect(set(expr) == {"op", "args"}, f"{where}: unrecognized predicate node")
    op = expr.get("op")
    args = expr.get("args")
    _expect(isinstance(op, str), f"{where}: predicate op must be a string")
    _expect(isinstance(args, list), f"{where}: predicate args must be a list")

    if op == "not":
        _expect(len(args) == 1, f"{where}: not requires exactly one arg")
    elif op in {"eq", "lt", "le", "gt", "ge", "and", "or"}:
        _expect(len(args) == 2, f"{where}: {op} requires exactly two args")
    else:
        _fail(f"{where}: unsupported predicate op '{op}'")

    arg_types = [
        _predicate_type(
            arg,
            env_types=env_types,
            result_type=result_type,
            allow_result=allow_result,
            where=f"{where}.args[{index}]",
            depth=depth + 1,
            nodes=nodes,
        )
        for index, arg in enumerate(args)
    ]

    if op == "eq":
        _expect(arg_types[0] == arg_types[1], f"{where}: eq args must have identical types")
        _expect(arg_types[0] != "unit", f"{where}: unit is not comparable")
        return "bool"
    if op in {"lt", "le", "gt", "ge"}:
        same_integer_type = (
            arg_types[0] == arg_types[1]
            and (arg_types[0] == "i64" or is_range_type(arg_types[0]))
        )
        _expect(
            same_integer_type,
            f"{where}: {op} requires identical i64 or range args",
        )
        return "bool"
    if op == "not":
        _expect(arg_types[0] == "bool", f"{where}: not requires bool arg")
        return "bool"

    _expect(arg_types[0] == arg_types[1] == "bool", f"{where}: {op} requires bool args")
    return "bool"


def _verify_contract_list(
    raw: Any,
    *,
    env_types: dict[str, Any],
    result_type: Any,
    allow_result: bool,
    where: str,
) -> set[str]:
    _expect(isinstance(raw, list), f"{where} must be a list")
    _expect(len(raw) <= MAX_CONTRACTS_PER_KIND, f"{where} may contain at most {MAX_CONTRACTS_PER_KIND} contracts")

    ids: set[str] = set()
    for index, clause in enumerate(raw):
        clause_where = f"{where}[{index}]"
        _expect(isinstance(clause, dict), f"{clause_where}: contract must be an object")
        _expect(
            set(clause) == {"id", "message", "predicate"},
            f"{clause_where}: contract must contain exactly 'id', 'message', and 'predicate'",
        )
        contract_id = clause.get("id")
        _expect(
            isinstance(contract_id, str) and CONTRACT_ID_RE.fullmatch(contract_id) is not None,
            f"{clause_where}: contract id must match [a-z][a-z0-9_.-]{{0,63}}",
        )
        _expect(contract_id not in ids, f"{clause_where}: duplicate contract id '{contract_id}'")
        ids.add(contract_id)

        message = clause.get("message")
        _expect(
            isinstance(message, str) and 1 <= len(message) <= MAX_CONTRACT_MESSAGE_LENGTH,
            f"{clause_where}: contract message length must be in [1, {MAX_CONTRACT_MESSAGE_LENGTH}]",
        )

        nodes = [0]
        predicate_type = _predicate_type(
            clause.get("predicate"),
            env_types=env_types,
            result_type=result_type,
            allow_result=allow_result,
            where=f"{clause_where}.predicate",
            depth=1,
            nodes=nodes,
        )
        _expect(predicate_type == "bool", f"{clause_where}: contract predicate must have type 'bool'")
    return ids


def verify_function_contracts(
    *,
    requires: Any,
    ensures: Any,
    env_types: dict[str, Any],
    result_type: Any,
    function_name: str,
) -> None:
    require_ids = _verify_contract_list(
        requires,
        env_types=env_types,
        result_type=result_type,
        allow_result=False,
        where=f"{function_name}: requires",
    )
    ensure_ids = _verify_contract_list(
        ensures,
        env_types=env_types,
        result_type=result_type,
        allow_result=True,
        where=f"{function_name}: ensures",
    )
    overlap = sorted(require_ids & ensure_ids)
    _expect(not overlap, f"{function_name}: contract ids must be unique across requires/ensures: {overlap}")


def _eval_expr(
    expr: dict[str, Any],
    *,
    values: dict[str, Any],
    result_value: Any,
    allow_result: bool,
    budget: ExecutionBudget,
    where: str,
) -> Any:
    budget.consume_step(where)

    if set(expr) == {"var"}:
        return values[expr["var"]]
    if set(expr) == {"result"}:
        if not allow_result:
            raise RuntimeError("verified precondition unexpectedly referenced result")
        return result_value
    if set(expr) == {"const"}:
        return expr["const"]["value"]

    op = expr["op"]
    args = expr["args"]
    evaluated = [
        _eval_expr(
            arg,
            values=values,
            result_value=result_value,
            allow_result=allow_result,
            budget=budget,
            where=f"{where}.args[{index}]",
        )
        for index, arg in enumerate(args)
    ]

    if op == "eq":
        return evaluated[0] == evaluated[1]
    if op == "lt":
        return evaluated[0] < evaluated[1]
    if op == "le":
        return evaluated[0] <= evaluated[1]
    if op == "gt":
        return evaluated[0] > evaluated[1]
    if op == "ge":
        return evaluated[0] >= evaluated[1]
    if op == "not":
        return not evaluated[0]
    if op == "and":
        return evaluated[0] and evaluated[1]
    if op == "or":
        return evaluated[0] or evaluated[1]
    raise RuntimeError(f"unsupported verified contract op {op!r}")


def evaluate_contracts(
    clauses: list[dict[str, Any]],
    *,
    values: dict[str, Any],
    result_value: Any,
    allow_result: bool,
    budget: ExecutionBudget,
    function_name: str,
    kind: str,
) -> None:
    trap_code = "apl.precondition_failed" if kind == "requires" else "apl.postcondition_failed"
    for index, clause in enumerate(clauses):
        where = f"{function_name}.{kind}[{index}]"
        passed = _eval_expr(
            clause["predicate"],
            values=values,
            result_value=result_value,
            allow_result=allow_result,
            budget=budget,
            where=f"{where}.predicate",
        )
        if not passed:
            raise ExecutionError(
                trap_code,
                f"contract '{clause['id']}' failed: {clause['message']}",
                where=where,
            )
