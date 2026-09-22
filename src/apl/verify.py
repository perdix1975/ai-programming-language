from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from . import SUPPORTED_LANGUAGE_VERSIONS
from .contracts import verify_function_contracts, verify_invariant_predicate
from .errors import VerificationError
from .invariants import (
    INVARIANT_NAME_RE,
    MAX_INVARIANTS,
    MAX_INVARIANT_MESSAGE_LENGTH,
    MAX_INVARIANT_PARAMS,
)
from .quantities import (
    MAX_UNIT_EXPONENT,
    MAX_UNIT_TERMS,
    UNIT_SYMBOL_RE,
    combine_quantity_types,
    is_quantity_type,
)
from .ranges import I64_MAX, I64_MIN, is_range_type
from .resources import RESOURCE_LIMIT_MAXIMA

SUPPORTED_TYPES = {"i64", "bool", "string", "unit"}
VERSION_LEVELS = {"0.0.1": 1, "0.0.2": 2, "0.0.3": 3, "0.0.4": 4, "0.0.5": 5, "0.0.6": 6, "0.0.7": 7, "0.0.8": 8, "0.0.9": 9, "0.0.10": 10, "0.0.11": 11, "0.0.12": 12, "0.0.13": 13, "0.0.14": 14}
MAX_REPEAT_BOUND = 1_000_000
MAX_ARRAY_LENGTH = 65_536
MAX_RECORD_FIELDS = 256
TRAP_CODE_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
MAX_TRAP_MESSAGE_LENGTH = 512
EFFECT_LEVELS = {"console.write": 8, "fs.read_text": 9, "net.get_text": 9}


@dataclass(frozen=True)
class Signature:
    params: tuple[Any, ...]
    returns: Any
    effects: tuple[str, ...]


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _value_type(name: str, env: dict[str, Any], where: str) -> Any:
    _expect(name in env, f"{where}: reference '{name}' is not defined before use")
    return env[name]


def _supports(version: str, level: int) -> bool:
    return VERSION_LEVELS[version] >= level


def _validate_effect_list(raw: Any, version: str, where: str) -> tuple[str, ...]:
    _expect(isinstance(raw, list), f"{where} must be a list")
    _expect(all(isinstance(item, str) for item in raw),
            f"{where} must contain only strings")
    for item in raw:
        _expect(item in EFFECT_LEVELS, f"{where}: unsupported effect '{item}'")
        _expect(
            _supports(version, EFFECT_LEVELS[item]),
            f"{where}: effect '{item}' requires APL 0.0.{EFFECT_LEVELS[item]}",
        )
    _expect(raw == sorted(set(raw)),
            f"{where} must be sorted lexicographically with no duplicates")
    return tuple(raw)


def _validate_program_limits(raw: Any) -> None:
    _expect(isinstance(raw, dict), "limits must be an object")
    _expect(
        set(raw) == set(RESOURCE_LIMIT_MAXIMA),
        "limits must contain exactly 'steps', 'output_lines', and 'host_reads'",
    )
    for name, maximum in RESOURCE_LIMIT_MAXIMA.items():
        value = raw.get(name)
        _expect(
            isinstance(value, int) and not isinstance(value, bool),
            f"limits.{name} must be an integer",
        )
        _expect(
            0 <= value <= maximum,
            f"limits.{name} must be in [0, {maximum}]",
        )


def _validate_type(raw: Any, version: str, where: str) -> None:
    if isinstance(raw, str):
        _expect(raw in SUPPORTED_TYPES, f"{where}: unsupported type '{raw}'")
        return

    _expect(isinstance(raw, dict),
            f"{where}: type must be a primitive name or structured descriptor")

    if set(raw) == {"quantity"}:
        _expect(_supports(version, 13),
                f"{where}: quantity types require APL 0.0.13")
        units = raw.get("quantity")
        _expect(isinstance(units, dict),
                f"{where}: quantity descriptor must be an object")
        _expect(
            len(units) <= MAX_UNIT_TERMS,
            f"{where}: quantity may contain at most {MAX_UNIT_TERMS} unit terms",
        )
        for symbol, exponent in units.items():
            _expect(
                isinstance(symbol, str) and UNIT_SYMBOL_RE.fullmatch(symbol) is not None,
                f"{where}: invalid unit symbol '{symbol}'",
            )
            _expect(
                isinstance(exponent, int) and not isinstance(exponent, bool),
                f"{where}: unit exponent for '{symbol}' must be an integer",
            )
            _expect(
                exponent != 0 and -MAX_UNIT_EXPONENT <= exponent <= MAX_UNIT_EXPONENT,
                f"{where}: unit exponent for '{symbol}' must be in "
                f"[-{MAX_UNIT_EXPONENT}, {MAX_UNIT_EXPONENT}] excluding 0",
            )
        return

    if set(raw) == {"range"}:
        _expect(_supports(version, 12),
                f"{where}: range types require APL 0.0.12")
        spec = raw.get("range")
        _expect(
            isinstance(spec, dict) and set(spec) == {"min", "max"},
            f"{where}: range descriptor must contain exactly 'min' and 'max'",
        )
        minimum = spec.get("min")
        maximum = spec.get("max")
        _expect(
            isinstance(minimum, int) and not isinstance(minimum, bool),
            f"{where}: range min must be an i64 integer literal",
        )
        _expect(
            isinstance(maximum, int) and not isinstance(maximum, bool),
            f"{where}: range max must be an i64 integer literal",
        )
        _expect(
            I64_MIN <= minimum <= I64_MAX,
            f"{where}: range min must be within i64 bounds",
        )
        _expect(
            I64_MIN <= maximum <= I64_MAX,
            f"{where}: range max must be within i64 bounds",
        )
        _expect(minimum <= maximum, f"{where}: range min must not exceed max")
        return

    if set(raw) == {"array", "len"}:
        _expect(_supports(version, 5),
                f"{where}: array types require APL 0.0.5")
        length = raw.get("len")
        _expect(isinstance(length, int) and not isinstance(length, bool),
                f"{where}: array length must be an integer literal")
        _expect(0 <= length <= MAX_ARRAY_LENGTH,
                f"{where}: array length must be in [0, {MAX_ARRAY_LENGTH}]")
        element = raw.get("array")
        _validate_type(element, version, f"{where}.array")
        _expect(element != "unit", f"{where}: array element type cannot be unit")
        return

    if set(raw) == {"record"}:
        _expect(_supports(version, 6),
                f"{where}: record types require APL 0.0.6")
        fields = raw.get("record")
        _expect(isinstance(fields, dict),
                f"{where}: record descriptor must map field names to types")
        _expect(len(fields) <= MAX_RECORD_FIELDS,
                f"{where}: record may contain at most {MAX_RECORD_FIELDS} fields")
        for field_name, field_type in fields.items():
            _expect(isinstance(field_name, str) and bool(field_name),
                    f"{where}: record field names must be non-empty strings")
            _validate_type(field_type, version, f"{where}.record.{field_name}")
            _expect(field_type != "unit",
                    f"{where}: record field '{field_name}' cannot have type unit")
        return

    _fail(f"{where}: unrecognized structured type descriptor")


def _read_invariants(
    raw: Any,
    version: str,
) -> tuple[dict[str, tuple[Any, ...]], dict[str, dict[str, Any]]]:
    _expect(isinstance(raw, list), "invariants must be a list")
    _expect(
        len(raw) <= MAX_INVARIANTS,
        f"invariants may contain at most {MAX_INVARIANTS} definitions",
    )

    signatures: dict[str, tuple[Any, ...]] = {}
    nodes: dict[str, dict[str, Any]] = {}

    for index, invariant in enumerate(raw):
        where = f"invariants[{index}]"
        _expect(isinstance(invariant, dict), f"{where}: invariant must be an object")
        _expect(
            set(invariant) == {"name", "params", "message", "predicate"},
            f"{where}: invariant must contain exactly 'name', 'params', 'message', and 'predicate'",
        )

        name = invariant.get("name")
        _expect(
            isinstance(name, str) and INVARIANT_NAME_RE.fullmatch(name) is not None,
            f"{where}: invariant name must match [a-z][a-z0-9_.-]{{0,63}}",
        )
        _expect(name not in signatures, f"{where}: duplicate invariant '{name}'")

        params = invariant.get("params")
        _expect(isinstance(params, list), f"{where}: params must be a list")
        _expect(
            len(params) <= MAX_INVARIANT_PARAMS,
            f"{where}: invariant may contain at most {MAX_INVARIANT_PARAMS} parameters",
        )
        param_names: set[str] = set()
        param_types: list[Any] = []
        for param_index, param in enumerate(params):
            param_where = f"{where}.params[{param_index}]"
            _expect(
                isinstance(param, dict) and set(param) == {"name", "type"},
                f"{param_where}: parameter must contain exactly 'name' and 'type'",
            )
            param_name = param.get("name")
            param_type = param.get("type")
            _expect(
                isinstance(param_name, str) and bool(param_name),
                f"{param_where}: parameter name must be non-empty",
            )
            _expect(
                param_name not in param_names,
                f"{param_where}: duplicate parameter '{param_name}'",
            )
            _validate_type(param_type, version, f"{param_where}.type")
            _expect(param_type != "unit", f"{param_where}: invariant parameter cannot be unit")
            param_names.add(param_name)
            param_types.append(param_type)

        message = invariant.get("message")
        _expect(
            isinstance(message, str)
            and 1 <= len(message) <= MAX_INVARIANT_MESSAGE_LENGTH,
            f"{where}: invariant message length must be in [1, {MAX_INVARIANT_MESSAGE_LENGTH}]",
        )

        signatures[name] = tuple(param_types)
        nodes[name] = invariant

    for name, invariant in nodes.items():
        verify_invariant_predicate(
            predicate=invariant["predicate"],
            env_types={
                param["name"]: param["type"]
                for param in invariant["params"]
            },
            where=f"invariant '{name}'.predicate",
        )

    return signatures, nodes


def _is_array_type(raw: Any) -> bool:
    return isinstance(raw, dict) and set(raw) == {"array", "len"}


def _is_record_type(raw: Any) -> bool:
    return isinstance(raw, dict) and set(raw) == {"record"} and isinstance(raw.get("record"), dict)


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

    capabilities: tuple[str, ...] = ()
    if _supports(version, 8):
        capabilities = _validate_effect_list(program.get("capabilities"), version, "capabilities")
    if _supports(version, 10):
        _validate_program_limits(program.get("limits"))

    invariant_signatures: dict[str, tuple[Any, ...]] = {}
    invariant_nodes: dict[str, dict[str, Any]] = {}
    if _supports(version, 14):
        invariant_signatures, invariant_nodes = _read_invariants(
            program.get("invariants"), version
        )
    else:
        _expect(
            "invariants" not in program,
            "invariant declarations require APL 0.0.14",
        )

    signatures: dict[str, Signature] = {}
    function_nodes: dict[str, dict[str, Any]] = {}
    for fn in functions:
        name, sig = _read_signature(fn, version, invariant_signatures if _supports(version, 14) else None)
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
            invariant_signatures=invariant_signatures,
        )

    _verify_acyclic_calls(call_graph)

    if _supports(version, 8):
        required_capabilities = tuple(sorted({
            effect
            for signature in signatures.values()
            for effect in signature.effects
        }))
        _expect(
            capabilities == required_capabilities,
            "capabilities must exactly match the union of declared function effects: "
            f"expected {list(required_capabilities)}, got {list(capabilities)}",
        )


def _read_signature(
    fn: Any,
    version: str,
    invariant_signatures: dict[str, tuple[Any, ...]] | None,
) -> tuple[str, Signature]:
    _expect(isinstance(fn, dict), "function must be an object")
    name = fn.get("name")
    _expect(isinstance(name, str) and bool(name), "function name must be non-empty")

    params = fn.get("params")
    _expect(isinstance(params, list), f"{name}: params must be a list")
    param_names: set[str] = set()
    param_types: list[Any] = []
    for param in params:
        _expect(isinstance(param, dict), f"{name}: parameter must be an object")
        p_name = param.get("name")
        p_type = param.get("type")
        _expect(isinstance(p_name, str) and bool(p_name), f"{name}: invalid parameter name")
        _expect(p_name not in param_names, f"{name}: duplicate parameter '{p_name}'")
        _validate_type(p_type, version, f"{name}: parameter '{p_name}'")
        param_names.add(p_name)
        param_types.append(p_type)

    returns = fn.get("returns")
    _validate_type(returns, version, f"{name}: return type")

    effects: tuple[str, ...] = ()
    if _supports(version, 8):
        effects = _validate_effect_list(fn.get("effects"), version, f"{name}: effects")

    if _supports(version, 11):
        verify_function_contracts(
            requires=fn.get("requires"),
            ensures=fn.get("ensures"),
            env_types={param["name"]: param["type"] for param in params},
            result_type=returns,
            function_name=name,
            invariant_signatures=invariant_signatures,
        )
    else:
        _expect(
            "requires" not in fn and "ensures" not in fn,
            f"{name}: function contracts require APL 0.0.11",
        )

    body = fn.get("body")
    _expect(isinstance(body, list) and body, f"{name}: body must be non-empty")
    return name, Signature(tuple(param_types), returns, effects)


def _verify_function_body(
    *,
    fn: dict[str, Any],
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    invariant_signatures: dict[str, tuple[Any, ...]],
) -> None:
    name = fn["name"]
    env = {p["name"]: p["type"] for p in fn["params"]}
    used_effects: set[str] = set()
    _verify_sequence(
        instructions=fn["body"],
        env=env,
        function_name=name,
        version=version,
        signatures=signatures,
        call_graph=call_graph,
        effects_used=used_effects,
        terminator="return",
        result_type=fn["returns"],
        where_prefix=name,
        invariant_signatures=invariant_signatures,
    )
    if _supports(version, 8):
        declared = set(signatures[name].effects)
        _expect(
            used_effects == declared,
            f"{name}: declared effects {sorted(declared)} do not match "
            f"inferred effects {sorted(used_effects)}",
        )


def _verify_sequence(
    *,
    instructions: Any,
    env: dict[str, Any],
    function_name: str,
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    effects_used: set[str],
    terminator: str,
    result_type: Any,
    where_prefix: str,
    invariant_signatures: dict[str, tuple[Any, ...]],
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

        if op == "trap":
            _expect(_supports(version, 7), f"{where}: trap requires APL 0.0.7")
            _verify_trap(ins, where)
            terminated = True
            continue

        _expect(op not in {"return", "yield", "trap"},
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
            effects_used.add("console.write")
        elif op == "call":
            _expect(_supports(version, 2), f"{where}: call requires APL 0.0.2+")
            _verify_call(
                ins, env, function_name, signatures, call_graph, effects_used, where
            )
        elif op == "if":
            _expect(_supports(version, 2), f"{where}: if requires APL 0.0.2+")
            _verify_if(
                ins=ins,
                env=env,
                function_name=function_name,
                version=version,
                signatures=signatures,
                call_graph=call_graph,
                effects_used=effects_used,
                where=where,
                invariant_signatures=invariant_signatures,
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
                effects_used=effects_used,
                where=where,
                invariant_signatures=invariant_signatures,
            )
        elif op == "array":
            _expect(_supports(version, 5), f"{where}: array requires APL 0.0.5")
            _verify_array(ins, env, version, where)
        elif op == "array.get":
            _expect(_supports(version, 5), f"{where}: array.get requires APL 0.0.5")
            _verify_array_get(ins, env, where)
        elif op == "array.len":
            _expect(_supports(version, 5), f"{where}: array.len requires APL 0.0.5")
            _verify_array_len(ins, env, where)
        elif op == "record":
            _expect(_supports(version, 6), f"{where}: record requires APL 0.0.6")
            _verify_record(ins, env, version, where)
        elif op == "record.get":
            _expect(_supports(version, 6), f"{where}: record.get requires APL 0.0.6")
            _verify_record_get(ins, env, where)
        elif op == "range.check":
            _expect(_supports(version, 12), f"{where}: range.check requires APL 0.0.12")
            _verify_range_check(ins, env, version, where)
        elif op == "range.value":
            _expect(_supports(version, 12), f"{where}: range.value requires APL 0.0.12")
            _verify_range_value(ins, env, where)
        elif op == "invariant.check":
            _expect(_supports(version, 14), f"{where}: invariant.check requires APL 0.0.14")
            _verify_invariant_check(ins, env, invariant_signatures, where)
        elif op == "quantity.attach":
            _expect(_supports(version, 13), f"{where}: quantity.attach requires APL 0.0.13")
            _verify_quantity_attach(ins, env, version, where)
        elif op == "quantity.value":
            _expect(_supports(version, 13), f"{where}: quantity.value requires APL 0.0.13")
            _verify_quantity_value(ins, env, where)
        elif op in {"quantity.add", "quantity.sub"}:
            _expect(_supports(version, 13), f"{where}: {op} requires APL 0.0.13")
            _verify_quantity_add_sub(ins, env, where, op)
        elif op in {"quantity.mul", "quantity.div"}:
            _expect(_supports(version, 13), f"{where}: {op} requires APL 0.0.13")
            _verify_quantity_mul_div(ins, env, version, where, op)
        elif op == "fs.read_text":
            _expect(_supports(version, 9), f"{where}: fs.read_text requires APL 0.0.9")
            _verify_host_text_read(ins, env, where, "fs.read_text")
            effects_used.add("fs.read_text")
        elif op == "net.get_text":
            _expect(_supports(version, 9), f"{where}: net.get_text requires APL 0.0.9")
            _verify_host_text_read(ins, env, where, "net.get_text")
            effects_used.add("net.get_text")
        else:
            _fail(f"{where}: unsupported op '{op}'")

    _expect(terminated, f"{where_prefix}: block must end with {terminator}")


def _bind_result(ins: dict[str, Any], env: dict[str, Any], inferred_type: Any, where: str) -> None:
    result = ins.get("id")
    declared = ins.get("type")
    _expect(isinstance(result, str) and bool(result), f"{where}: result id is required")
    _expect(result not in env, f"{where}: SSA id '{result}' is already defined")
    _expect(declared == inferred_type,
            f"{where}: declared type '{declared}' does not match inferred '{inferred_type}'")
    env[result] = inferred_type


def _verify_const(ins: dict[str, Any], env: dict[str, Any], where: str) -> None:
    typ = ins.get("type")
    _expect(isinstance(typ, str) and typ in SUPPORTED_TYPES - {"unit"},
            f"{where}: invalid const type '{typ}'")
    value = ins.get("value")

    valid = (
        (typ == "i64" and isinstance(value, int) and not isinstance(value, bool)
         and -(2**63) <= value <= 2**63 - 1)
        or (typ == "bool" and isinstance(value, bool))
        or (typ == "string" and isinstance(value, str))
    )
    _expect(valid, f"{where}: constant value does not match type '{typ}'")
    _bind_result(ins, env, typ, where)


def _binary_args(ins: dict[str, Any], env: dict[str, Any], where: str) -> tuple[Any, Any]:
    args = ins.get("args")
    _expect(isinstance(args, list) and len(args) == 2,
            f"{where}: binary op requires exactly two args")
    _expect(all(isinstance(x, str) for x in args), f"{where}: args must be SSA ids")
    return _value_type(args[0], env, where), _value_type(args[1], env, where)


def _verify_binary_i64(ins: dict[str, Any], env: dict[str, Any], where: str) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(left == right == "i64", f"{where}: arithmetic requires i64 operands")
    _bind_result(ins, env, "i64", where)


def _verify_ordered_i64(ins: dict[str, Any], env: dict[str, Any], where: str) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(left == right == "i64", f"{where}: ordered comparison requires i64 operands")
    _bind_result(ins, env, "bool", where)


def _verify_eq(ins: dict[str, Any], env: dict[str, Any], where: str) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(left == right, f"{where}: eq operands must have identical types")
    _expect(left != "unit", f"{where}: unit is not comparable")
    _bind_result(ins, env, "bool", where)


def _verify_print(ins: dict[str, Any], env: dict[str, Any], where: str) -> None:
    args = ins.get("args")
    _expect(isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
            f"{where}: print requires exactly one SSA id")
    typ = _value_type(args[0], env, where)
    _expect(isinstance(typ, str) and typ in {"i64", "bool", "string"},
            f"{where}: print currently supports only scalar values")


def _verify_call(
    ins: dict[str, Any],
    env: dict[str, Any],
    function_name: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    effects_used: set[str],
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
    effects_used.update(sig.effects)
    if sig.returns == "unit":
        _expect("id" not in ins, f"{where}: unit call must not bind an id")
        _expect("type" not in ins or ins.get("type") == "unit",
                f"{where}: unit call type must be omitted or 'unit'")
    else:
        _bind_result(ins, env, sig.returns, where)


def _verify_if(
    *,
    ins: dict[str, Any],
    env: dict[str, Any],
    function_name: str,
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    effects_used: set[str],
    where: str,
    invariant_signatures: dict[str, tuple[Any, ...]],
) -> None:
    cond = ins.get("cond")
    _expect(isinstance(cond, str), f"{where}: if cond must be an SSA id")
    _expect(_value_type(cond, env, where) == "bool",
            f"{where}: if condition must have type 'bool'")

    result_type = ins.get("type")
    _validate_type(result_type, version, f"{where}: if result type")
    _expect(result_type != "unit",
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
            effects_used=effects_used,
            terminator="yield",
            result_type=result_type,
            where_prefix=f"{where}.{label}",
            invariant_signatures=invariant_signatures,
        )

    _bind_result(ins, env, result_type, where)


def _verify_repeat(
    *,
    ins: dict[str, Any],
    env: dict[str, Any],
    function_name: str,
    version: str,
    signatures: dict[str, Signature],
    call_graph: dict[str, set[str]],
    effects_used: set[str],
    where: str,
    invariant_signatures: dict[str, tuple[Any, ...]],
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
        effects_used=effects_used,
        terminator="yield",
        result_type=result_type,
        where_prefix=f"{where}.body",
        invariant_signatures=invariant_signatures,
    )

    _bind_result(ins, env, result_type, where)


def _verify_array(
    ins: dict[str, Any],
    env: dict[str, Any],
    version: str,
    where: str,
) -> None:
    typ = ins.get("type")
    _validate_type(typ, version, f"{where}: array result type")
    _expect(_is_array_type(typ), f"{where}: array op requires an array result type")

    args = ins.get("args")
    _expect(isinstance(args, list), f"{where}: array args must be a list")
    expected_len = typ["len"]
    _expect(len(args) == expected_len,
            f"{where}: array type length is {expected_len}, got {len(args)} values")

    element_type = typ["array"]
    for index, arg in enumerate(args):
        _expect(isinstance(arg, str), f"{where}: array arg {index} must be an SSA id")
        actual = _value_type(arg, env, where)
        _expect(actual == element_type,
                f"{where}: array arg {index} has incompatible element type")

    _bind_result(ins, env, typ, where)


def _verify_array_get(
    ins: dict[str, Any], env: dict[str, Any], where: str
) -> None:
    args = ins.get("args")
    _expect(isinstance(args, list) and len(args) == 2,
            f"{where}: array.get requires array and index args")
    _expect(all(isinstance(arg, str) for arg in args),
            f"{where}: array.get args must be SSA ids")

    array_type = _value_type(args[0], env, where)
    _expect(_is_array_type(array_type),
            f"{where}: first array.get arg must be an array")
    _expect(_value_type(args[1], env, where) == "i64",
            f"{where}: array.get index must have type 'i64'")
    _bind_result(ins, env, array_type["array"], where)


def _verify_array_len(
    ins: dict[str, Any], env: dict[str, Any], where: str
) -> None:
    args = ins.get("args")
    _expect(isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
            f"{where}: array.len requires exactly one array SSA id")
    array_type = _value_type(args[0], env, where)
    _expect(_is_array_type(array_type),
            f"{where}: array.len arg must be an array")
    _bind_result(ins, env, "i64", where)


def _verify_invariant_check(
    ins: dict[str, Any],
    env: dict[str, Any],
    invariant_signatures: dict[str, tuple[Any, ...]],
    where: str,
) -> None:
    _expect(
        set(ins) == {"op", "invariant", "args"},
        f"{where}: invariant.check must contain exactly 'op', 'invariant', and 'args'",
    )
    name = ins.get("invariant")
    _expect(
        isinstance(name, str) and name in invariant_signatures,
        f"{where}: unknown invariant '{name}'",
    )
    args = ins.get("args")
    _expect(isinstance(args, list), f"{where}: invariant.check args must be a list")
    expected_types = invariant_signatures[name]
    _expect(
        len(args) == len(expected_types),
        f"{where}: invariant '{name}' expects {len(expected_types)} args, got {len(args)}",
    )
    for index, (arg, expected_type) in enumerate(zip(args, expected_types)):
        _expect(
            isinstance(arg, str),
            f"{where}: invariant.check arg {index} must be an SSA id",
        )
        actual_type = _value_type(arg, env, where)
        _expect(
            actual_type == expected_type,
            f"{where}: invariant arg {index} expects '{expected_type}', got '{actual_type}'",
        )


def _verify_quantity_attach(
    ins: dict[str, Any],
    env: dict[str, Any],
    version: str,
    where: str,
) -> None:
    typ = ins.get("type")
    _validate_type(typ, version, f"{where}: quantity.attach result type")
    _expect(is_quantity_type(typ), f"{where}: quantity.attach requires a quantity result type")
    args = ins.get("args")
    _expect(
        isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
        f"{where}: quantity.attach requires exactly one i64 SSA id",
    )
    _expect(
        _value_type(args[0], env, where) == "i64",
        f"{where}: quantity.attach source must have type 'i64'",
    )
    _bind_result(ins, env, typ, where)


def _verify_quantity_value(
    ins: dict[str, Any],
    env: dict[str, Any],
    where: str,
) -> None:
    args = ins.get("args")
    _expect(
        isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
        f"{where}: quantity.value requires exactly one quantity SSA id",
    )
    source_type = _value_type(args[0], env, where)
    _expect(is_quantity_type(source_type), f"{where}: quantity.value source must be a quantity")
    _bind_result(ins, env, "i64", where)


def _verify_quantity_add_sub(
    ins: dict[str, Any],
    env: dict[str, Any],
    where: str,
    op: str,
) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(
        is_quantity_type(left) and left == right,
        f"{where}: {op} requires identical quantity operand types",
    )
    _bind_result(ins, env, left, where)


def _verify_quantity_mul_div(
    ins: dict[str, Any],
    env: dict[str, Any],
    version: str,
    where: str,
    op: str,
) -> None:
    left, right = _binary_args(ins, env, where)
    _expect(
        is_quantity_type(left) and is_quantity_type(right),
        f"{where}: {op} requires quantity operands",
    )
    try:
        inferred = combine_quantity_types(left, right, divide=op == "quantity.div")
    except ValueError as exc:
        _fail(f"{where}: {exc}")
    _validate_type(inferred, version, f"{where}: derived quantity type")
    _bind_result(ins, env, inferred, where)


def _verify_range_check(
    ins: dict[str, Any],
    env: dict[str, Any],
    version: str,
    where: str,
) -> None:
    typ = ins.get("type")
    _validate_type(typ, version, f"{where}: range.check result type")
    _expect(is_range_type(typ), f"{where}: range.check requires a range result type")
    args = ins.get("args")
    _expect(
        isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
        f"{where}: range.check requires exactly one i64 SSA id",
    )
    _expect(
        _value_type(args[0], env, where) == "i64",
        f"{where}: range.check source must have type 'i64'",
    )
    _bind_result(ins, env, typ, where)


def _verify_range_value(
    ins: dict[str, Any],
    env: dict[str, Any],
    where: str,
) -> None:
    args = ins.get("args")
    _expect(
        isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
        f"{where}: range.value requires exactly one range SSA id",
    )
    source_type = _value_type(args[0], env, where)
    _expect(is_range_type(source_type), f"{where}: range.value source must be a range")
    _bind_result(ins, env, "i64", where)


def _verify_host_text_read(
    ins: dict[str, Any],
    env: dict[str, Any],
    where: str,
    op: str,
) -> None:
    args = ins.get("args")
    _expect(
        isinstance(args, list) and len(args) == 1 and isinstance(args[0], str),
        f"{where}: {op} requires exactly one string SSA id",
    )
    _expect(
        _value_type(args[0], env, where) == "string",
        f"{where}: {op} argument must have type 'string'",
    )
    _bind_result(ins, env, "string", where)


def _verify_record(
    ins: dict[str, Any],
    env: dict[str, Any],
    version: str,
    where: str,
) -> None:
    typ = ins.get("type")
    _validate_type(typ, version, f"{where}: record result type")
    _expect(_is_record_type(typ), f"{where}: record op requires a record result type")

    fields = ins.get("fields")
    _expect(isinstance(fields, dict), f"{where}: record fields must be an object")
    expected_fields = typ["record"]
    _expect(set(fields) == set(expected_fields),
            f"{where}: record fields must exactly match the record type")

    for field_name, source in fields.items():
        _expect(isinstance(source, str),
                f"{where}: record field '{field_name}' must reference an SSA id")
        actual = _value_type(source, env, where)
        _expect(actual == expected_fields[field_name],
                f"{where}: record field '{field_name}' has incompatible type")

    _bind_result(ins, env, typ, where)


def _verify_record_get(
    ins: dict[str, Any], env: dict[str, Any], where: str
) -> None:
    record_name = ins.get("record")
    field_name = ins.get("field")
    _expect(isinstance(record_name, str),
            f"{where}: record.get record must be an SSA id")
    _expect(isinstance(field_name, str) and bool(field_name),
            f"{where}: record.get field must be a non-empty string")

    record_type = _value_type(record_name, env, where)
    _expect(_is_record_type(record_type),
            f"{where}: record.get source must be a record")
    fields = record_type["record"]
    _expect(field_name in fields,
            f"{where}: record field '{field_name}' does not exist")
    _bind_result(ins, env, fields[field_name], where)


def _verify_trap(ins: dict[str, Any], where: str) -> None:
    code = ins.get("code")
    message = ins.get("message")
    _expect(isinstance(code, str) and TRAP_CODE_RE.fullmatch(code) is not None,
            f"{where}: trap code must match [a-z][a-z0-9_.-]{{0,63}}")
    _expect(not code.startswith("apl.") and code != "apl",
            f"{where}: trap code namespace 'apl.*' is reserved")
    _expect(isinstance(message, str) and 1 <= len(message) <= MAX_TRAP_MESSAGE_LENGTH,
            f"{where}: trap message length must be in [1, {MAX_TRAP_MESSAGE_LENGTH}]")


def _verify_return(
    ins: dict[str, Any], env: dict[str, Any], returns: Any, where: str
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
    ins: dict[str, Any], env: dict[str, Any], expected_type: Any, where: str
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
