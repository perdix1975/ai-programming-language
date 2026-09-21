from __future__ import annotations

from typing import Any

from . import LANGUAGE_VERSION
from .errors import VerificationError

SUPPORTED_TYPES = {"i64", "bool", "string", "unit"}
VALUE_OPS = {"const", "add", "sub", "mul", "eq"}
EFFECT_OPS = {"print"}
TERMINATORS = {"return"}


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _value_type(name: str, env: dict[str, str], where: str) -> str:
    _expect(name in env, f"{where}: reference '{name}' is not defined before use")
    return env[name]


def verify_program(program: Any) -> None:
    _expect(isinstance(program, dict), "program must be an object")
    _expect(program.get("apl") == LANGUAGE_VERSION,
            f"unsupported APL version: expected {LANGUAGE_VERSION!r}")
    _expect(isinstance(program.get("module"), str) and bool(program["module"]),
            "module must be a non-empty string")
    _expect(isinstance(program.get("entry"), str) and bool(program["entry"]),
            "entry must be a non-empty string")

    functions = program.get("functions")
    _expect(isinstance(functions, list) and len(functions) > 0,
            "functions must be a non-empty list")

    seen_functions: set[str] = set()
    for fn in functions:
        _verify_function(fn, seen_functions)
    _expect(program["entry"] in seen_functions,
            f"entry function '{program['entry']}' does not exist")


def _verify_function(fn: Any, seen_functions: set[str]) -> None:
    _expect(isinstance(fn, dict), "function must be an object")
    name = fn.get("name")
    _expect(isinstance(name, str) and bool(name), "function name must be non-empty")
    _expect(name not in seen_functions, f"duplicate function '{name}'")
    seen_functions.add(name)

    params = fn.get("params")
    _expect(isinstance(params, list), f"{name}: params must be a list")
    env: dict[str, str] = {}
    for param in params:
        _expect(isinstance(param, dict), f"{name}: parameter must be an object")
        p_name = param.get("name")
        p_type = param.get("type")
        _expect(isinstance(p_name, str) and bool(p_name), f"{name}: invalid parameter name")
        _expect(p_name not in env, f"{name}: duplicate parameter '{p_name}'")
        _expect(p_type in SUPPORTED_TYPES, f"{name}: unsupported parameter type '{p_type}'")
        env[p_name] = p_type

    returns = fn.get("returns")
    _expect(returns in SUPPORTED_TYPES, f"{name}: unsupported return type '{returns}'")

    body = fn.get("body")
    _expect(isinstance(body, list) and body, f"{name}: body must be non-empty")
    _expect(body[-1].get("op") in TERMINATORS if isinstance(body[-1], dict) else False,
            f"{name}: body must end with return")

    terminated = False
    for index, ins in enumerate(body):
        where = f"{name}[{index}]"
        _expect(not terminated, f"{where}: instruction appears after terminator")
        _expect(isinstance(ins, dict), f"{where}: instruction must be an object")
        op = ins.get("op")
        _expect(isinstance(op, str), f"{where}: missing op")

        if op == "const":
            _verify_const(ins, env, where)
        elif op in {"add", "sub", "mul"}:
            _verify_binary_i64(ins, env, where)
        elif op == "eq":
            _verify_eq(ins, env, where)
        elif op == "print":
            _verify_print(ins, env, where)
        elif op == "return":
            _verify_return(ins, env, returns, where)
            terminated = True
        else:
            _fail(f"{where}: unsupported op '{op}'")


def _bind_result(ins: dict[str, Any], env: dict[str, str], inferred_type: str, where: str) -> None:
    result = ins.get("id")
    declared = ins.get("type")
    _expect(isinstance(result, str) and bool(result), f"{where}: result id is required")
    _expect(result not in env, f"{where}: SSA id '{result}' is already defined")
    _expect(declared == inferred_type,
            f"{where}: declared type '{declared}' does not match inferred '{inferred_type}'")
    env[result] = inferred_type


def _verify_const(ins: dict[str, Any], env: dict[str, str], where: str) -> None:
    typ = ins.get("type")
    _expect(typ in SUPPORTED_TYPES - {"unit"}, f"{where}: invalid const type '{typ}'")
    value = ins.get("value")

    valid = (
        (typ == "i64" and isinstance(value, int) and not isinstance(value, bool)
         and -(2**63) <= value <= 2**63 - 1)
        or (typ == "bool" and isinstance(value, bool))
        or (typ == "string" and isinstance(value, str))
    )
    _expect(valid, f"{where}: constant value does not match type '{typ}'")
    _bind_result(ins, env, typ, where)


def _binary_args(ins: dict[str, Any], env: dict[str, str], where: str) -> tuple[str, str]:
    args = ins.get("args")
    _expect(isinstance(args, list) and len(args) == 2,
            f"{where}: binary op requires exactly two args")
    _expect(all(isinstance(x, str) for x in args), f"{where}: args must be SSA ids")
    return _value_type(args[0], env, where), _value_type(args[1], env, where)


def _verify_binary_i64(ins: dict[str, Any], env: dict[str, str], where: str) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(left == right == "i64", f"{where}: arithmetic requires i64 operands")
    _bind_result(ins, env, "i64", where)


def _verify_eq(ins: dict[str, Any], env: dict[str, str], where: str) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(left == right, f"{where}: eq operands must have identical types")
    _expect(left != "unit", f"{where}: unit is not comparable")
    _bind_result(ins, env, "bool", where)


def _verify_print(ins: dict[str, Any], env: dict[str, str], where: str) -> None:
    args = ins.get("args")
    _expect(isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
            f"{where}: print requires exactly one SSA id")
    _value_type(args[0], env, where)


def _verify_return(
    ins: dict[str, Any], env: dict[str, str], returns: str, where: str
) -> None:
    if returns == "unit":
        _expect("value" not in ins or ins.get("value") is None,
                f"{where}: unit function must return no value")
        return
    value = ins.get("value")
    _expect(isinstance(value, str), f"{where}: return value must be an SSA id")
    actual = _value_type(value, env, where)
    _expect(actual == returns,
            f"{where}: returning '{actual}' from function returning '{returns}'")
