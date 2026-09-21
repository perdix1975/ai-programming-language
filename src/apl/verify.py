from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import SUPPORTED_LANGUAGE_VERSIONS
from .errors import VerificationError

SUPPORTED_TYPES = {"i64", "bool", "string", "unit"}
VERSION_LEVELS = {"0.0.1": 1, "0.0.2": 2, "0.0.3": 3, "0.0.4": 4}
MAX_REPEAT_BOUND = 1_000_000


@dataclass(frozen=True)
class Signature:
    params: tuple[str, ...]
    returns: str


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _value_type(name: str, env: dict[str, str], where: str) -> str:
    _expect(name in env, f"{where}: reference '{name}' is not defined before use")
    return env[name]


def _supports(version: str, level: int) -> bool:
    return VERSION_LEVELS[version] >= level


def verify_program(program: Any) -> None:
    _expect(isinstance(program, dict), "program must be an object")
    version = program.get("apl")
    _expect(version in SUPPORTED_LANGUAGE_VERSIONS,
            f"unsupported APL version '{version}'")
    _expect(isinstance(program.get("module"), str) and bool(program["module"]),
            "module must be a non-empty string")
    _expect(isinstance(program.get("entry"), str) and bool(program["entry"]),
            "entry must be a non-empty string")

    functions = program.get("functions")
    _expect(isinstance(functions, list) and len(functions) > 0,
            "functions must be a non-empty list")

    signatures: dict[str, Signature] = {}
    function_nodes: dict[str, dict[str, Any]] = {}
    for fn in functions:
        name, sig = _read_signature(fn)
        _expect(name not in signatures, f"duplicate function '{name}'")
        signatures[name] = sig
        function_nodes[name] = fn

    entry = program["entry"]
    _expect(entry in signatures, f"entry function '{entry}' does not exist")
    _expect(len(signatures[entry].params) == 0,
            f"entry function '{entry}' must not require parameters")

    call_graph: dict[str, set[str]] = {name: set() for name in signatures}
    for fn in function_nodes.values():
        _verify_function_body(
            fn=fn,
            version=version,
            signatures=signatures,
            call_graph=call_graph,
        )

    _verify_acyclic_calls(call_graph)


def _read_signature(fn: Any) -> tuple[str, Signature]:
    _expect(isinstance(fn, dict), "function must be an object")
    name = fn.get("name")
    _expect(isinstance(name, str) and bool(name), "function name must be non-empty")

    params = fn.get("params")
    _expect(isinstance(params, list), f"{name}: params must be a list")
    param_names: set[str] = set()
    param_types: list[str] = []
    for param in params:
        _expect(isinstance(param, dict), f"{name}: parameter must be an object")
        p_name = param.get("name")
        p_type = param.get("type")
        _expect(isinstance(p_name, str) and bool(p_name), f"{name}: invalid parameter name")
        _expect(p_name not in param_names, f"{name}: duplicate parameter '{p_name}'")
        _expect(p_type in SUPPORTED_TYPES, f"{name}: unsupported parameter type '{p_type}'")
        param_names.add(p_name)
        param_types.append(p_type)

    returns = fn.get("returns")
    _expect(returns in SUPPORTED_TYPES, f"{name}: unsupported return type '{returns}'")

    body = fn.get("body")
    _expect(isinstance(body, list) and body, f"{name}: body must be non-empty")
    return name, Signature(tuple(param_types), returns)


def _verify_function_body(
    *,
    fn: dict[str, Any],
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
) -> None:
    name = fn["name"]
    env = {p["name"]: p["type"] for p in fn["params"]}
    _verify_sequence(
        instructions=fn["body"],
        env=env,
        function_name=name,
        version=version,
        signatures=signatures,
        call_graph=call_graph,
        terminator="return",
        result_type=fn["returns"],
        where_prefix=name,
    )


def _verify_sequence(
    *,
    instructions: Any,
    env: dict[str, str],
    function_name: str,
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    terminator: str,
    result_type: str,
    where_prefix: str,
) -> None:
    _expect(isinstance(instructions, list) and instructions,
            f"{where_prefix}: block must be a non-empty list")

    terminated = False
    for index, ins in enumerate(instructions):
        where = f"{where_prefix}[{index}]"
        _expect(not terminated, f"{where}: instruction appears after terminator")
        _expect(isinstance(ins, dict), f"{where}: instruction must be an object")
        op = ins.get("op")
        _expect(isinstance(op, str), f"{where}: missing op")

        if op == terminator:
            if terminator == "return":
                _verify_return(ins, env, result_type, where)
            else:
                _verify_yield(ins, env, result_type, where)
            terminated = True
            continue

        _expect(op not in {"return", "yield"},
                f"{where}: '{op}' is not valid in this block")

        if op == "const":
            _verify_const(ins, env, where)
        elif op in {"add", "sub", "mul"}:
            _verify_binary_i64(ins, env, where)
        elif op in {"div", "rem"}:
            _expect(_supports(version, 3), f"{where}: {op} requires APL 0.0.3")
            _verify_binary_i64(ins, env, where)
        elif op in {"lt", "le", "gt", "ge"}:
            _expect(_supports(version, 3), f"{where}: {op} requires APL 0.0.3")
            _verify_ordered_i64(ins, env, where)
        elif op == "eq":
            _verify_eq(ins, env, where)
        elif op == "print":
            _verify_print(ins, env, where)
        elif op == "call":
            _expect(_supports(version, 2), f"{where}: call requires APL 0.0.2+")
            _verify_call(ins, env, function_name, signatures, call_graph, where)
        elif op == "if":
            _expect(_supports(version, 2), f"{where}: if requires APL 0.0.2+")
            _verify_if(
                ins=ins,
                env=env,
                function_name=function_name,
                version=version,
                signatures=signatures,
                call_graph=call_graph,
                where=where,
            )
        elif op == "repeat":
            _expect(_supports(version, 4), f"{where}: repeat requires APL 0.0.4")
            _verify_repeat(
                ins=ins,
                env=env,
                function_name=function_name,
                version=version,
                signatures=signatures,
                call_graph=call_graph,
                where=where,
            )
        else:
            _fail(f"{where}: unsupported op '{op}'")

    _expect(terminated, f"{where_prefix}: block must end with {terminator}")


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


def _verify_ordered_i64(ins: dict[str, Any], env: dict[str, str], where: str) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(left == right == "i64", f"{where}: ordered comparison requires i64 operands")
    _bind_result(ins, env, "bool", where)


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


def _verify_call(
    ins: dict[str, Any],
    env: dict[str, str],
    function_name: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    where: str,
) -> None:
    target = ins.get("function")
    _expect(isinstance(target, str) and target in signatures,
            f"{where}: unknown function '{target}'")
    sig = signatures[target]

    args = ins.get("args")
    _expect(isinstance(args, list), f"{where}: call args must be a list")
    _expect(len(args) == len(sig.params),
            f"{where}: function '{target}' expects {len(sig.params)} args, got {len(args)}")
    for index, (arg, expected_type) in enumerate(zip(args, sig.params)):
        _expect(isinstance(arg, str), f"{where}: call arg {index} must be an SSA id")
        actual = _value_type(arg, env, where)
        _expect(actual == expected_type,
                f"{where}: call arg {index} expects '{expected_type}', got '{actual}'")

    call_graph[function_name].add(target)
    if sig.returns == "unit":
        _expect("id" not in ins, f"{where}: unit call must not bind an id")
        _expect("type" not in ins or ins.get("type") == "unit",
                f"{where}: unit call type must be omitted or 'unit'")
    else:
        _bind_result(ins, env, sig.returns, where)


def _verify_if(
    *,
    ins: dict[str, Any],
    env: dict[str, str],
    function_name: str,
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    where: str,
) -> None:
    cond = ins.get("cond")
    _expect(isinstance(cond, str), f"{where}: if cond must be an SSA id")
    _expect(_value_type(cond, env, where) == "bool",
            f"{where}: if condition must have type 'bool'")

    result_type = ins.get("type")
    _expect(result_type in SUPPORTED_TYPES - {"unit"},
            f"{where}: if must produce a non-unit value")

    for label in ("then", "else"):
        branch_env = dict(env)
        _verify_sequence(
            instructions=ins.get(label),
            env=branch_env,
            function_name=function_name,
            version=version,
            signatures=signatures,
            call_graph=call_graph,
            terminator="yield",
            result_type=result_type,
            where_prefix=f"{where}.{label}",
        )

    _bind_result(ins, env, result_type, where)


def _verify_repeat(
    *,
    ins: dict[str, Any],
    env: dict[str, str],
    function_name: str,
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    where: str,
) -> None:
    count = ins.get("count")
    _expect(isinstance(count, str), f"{where}: repeat count must be an SSA id")
    _expect(_value_type(count, env, where) == "i64",
            f"{where}: repeat count must have type 'i64'")

    bound = ins.get("max")
    _expect(isinstance(bound, int) and not isinstance(bound, bool),
            f"{where}: repeat max must be an integer literal")
    _expect(0 <= bound <= MAX_REPEAT_BOUND,
            f"{where}: repeat max must be in [0, {MAX_REPEAT_BOUND}]")

    init = ins.get("init")
    _expect(isinstance(init, str), f"{where}: repeat init must be an SSA id")
    result_type = _value_type(init, env, where)
    _expect(result_type != "unit", f"{where}: repeat cannot carry unit")

    index_name = ins.get("index")
    carry_name = ins.get("carry")
    _expect(isinstance(index_name, str) and bool(index_name),
            f"{where}: repeat index must be a non-empty name")
    _expect(isinstance(carry_name, str) and bool(carry_name),
            f"{where}: repeat carry must be a non-empty name")
    _expect(index_name != carry_name,
            f"{where}: repeat index and carry names must differ")
    _expect(index_name not in env,
            f"{where}: repeat index '{index_name}' collides with an outer SSA id")
    _expect(carry_name not in env,
            f"{where}: repeat carry '{carry_name}' collides with an outer SSA id")

    branch_env = dict(env)
    branch_env[index_name] = "i64"
    branch_env[carry_name] = result_type
    _verify_sequence(
        instructions=ins.get("body"),
        env=branch_env,
        function_name=function_name,
        version=version,
        signatures=signatures,
        call_graph=call_graph,
        terminator="yield",
        result_type=result_type,
        where_prefix=f"{where}.body",
    )

    _bind_result(ins, env, result_type, where)


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


def _verify_yield(
    ins: dict[str, Any], env: dict[str, str], expected_type: str, where: str
) -> None:
    value = ins.get("value")
    _expect(isinstance(value, str), f"{where}: yield value must be an SSA id")
    actual = _value_type(value, env, where)
    _expect(actual == expected_type,
            f"{where}: yielding '{actual}' from branch requiring '{expected_type}'")


def _verify_acyclic_calls(call_graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            _fail(f"recursive call cycle detected at function '{name}'")
        if name in visited:
            return
        visiting.add(name)
        for target in call_graph[name]:
            visit(target)
        visiting.remove(name)
        visited.add(name)

    for name in call_graph:
        visit(name)
