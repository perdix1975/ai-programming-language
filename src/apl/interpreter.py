from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .errors import ExecutionError
from .verify import verify_program


@dataclass(frozen=True)
class RecordValue:
    fields: tuple[tuple[str, Any], ...]

    def get(self, name: str) -> Any:
        for field_name, value in self.fields:
            if field_name == name:
                return value
        raise KeyError(name)


@dataclass(frozen=True)
class ExecutionResult:
    value: Any
    type: Any


def _i64(value: int, where: str) -> int:
    if value < -(2**63) or value > 2**63 - 1:
        raise ExecutionError("apl.i64_overflow", "signed i64 overflow", where=where)
    return value


def _trunc_div(a: int, b: int, where: str) -> int:
    if b == 0:
        raise ExecutionError("apl.division_by_zero", "division by zero", where=where)
    if a == -(2**63) and b == -1:
        raise ExecutionError(f"{where}: signed i64 overflow")
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _trunc_rem(a: int, b: int, where: str) -> int:
    if b == 0:
        raise ExecutionError(f"{where}: division by zero")
    if a == -(2**63) and b == -1:
        return 0
    q = _trunc_div(a, b, where)
    return a - q * b


def run_program(
    program: dict[str, Any],
    *,
    output: Callable[[str], None] = print,
) -> ExecutionResult:
    verify_program(program)
    functions = {fn["name"]: fn for fn in program["functions"]}
    return _execute_function(
        functions=functions,
        function_name=program["entry"],
        arguments=[],
        output=output,
    )


def _execute_function(
    *,
    functions: dict[str, dict[str, Any]],
    function_name: str,
    arguments: list[Any],
    output: Callable[[str], None],
) -> ExecutionResult:
    fn = functions[function_name]
    env = {param["name"]: value for param, value in zip(fn["params"], arguments)}
    types = {param["name"]: param["type"] for param in fn["params"]}

    return _execute_sequence(
        instructions=fn["body"],
        env=env,
        types=types,
        functions=functions,
        function_name=function_name,
        output=output,
        terminator="return",
        result_type=fn["returns"],
        where_prefix=function_name,
    )


def _execute_sequence(
    *,
    instructions: list[dict[str, Any]],
    env: dict[str, Any],
    types: dict[str, Any],
    functions: dict[str, dict[str, Any]],
    function_name: str,
    output: Callable[[str], None],
    terminator: str,
    result_type: Any,
    where_prefix: str,
) -> ExecutionResult:
    for index, ins in enumerate(instructions):
        op = ins["op"]
        where = f"{where_prefix}[{index}]"

        if op == terminator:
            if result_type == "unit":
                return ExecutionResult(None, "unit")
            name = ins["value"]
            return ExecutionResult(env[name], types[name])

        if op == "trap":
            raise ExecutionError(ins["code"], ins["message"], where=where)

        if op == "const":
            env[ins["id"]] = ins["value"]
            types[ins["id"]] = ins["type"]
        elif op in {"add", "sub", "mul"}:
            a, b = (env[x] for x in ins["args"])
            raw = a + b if op == "add" else a - b if op == "sub" else a * b
            env[ins["id"]] = _i64(raw, where)
            types[ins["id"]] = "i64"
        elif op in {"div", "rem"}:
            a, b = (env[x] for x in ins["args"])
            env[ins["id"]] = _trunc_div(a, b, where) if op == "div" else _trunc_rem(a, b, where)
            types[ins["id"]] = "i64"
        elif op in {"lt", "le", "gt", "ge"}:
            a, b = (env[x] for x in ins["args"])
            env[ins["id"]] = (
                a < b if op == "lt" else
                a <= b if op == "le" else
                a > b if op == "gt" else
                a >= b
            )
            types[ins["id"]] = "bool"
        elif op == "eq":
            a, b = (env[x] for x in ins["args"])
            env[ins["id"]] = a == b
            types[ins["id"]] = "bool"
        elif op == "array":
            env[ins["id"]] = tuple(env[name] for name in ins["args"])
            types[ins["id"]] = ins["type"]
        elif op == "array.get":
            array_name, index_name = ins["args"]
            values = env[array_name]
            item_index = env[index_name]
            if item_index < 0 or item_index >= len(values):
                raise ExecutionError(
                    "apl.array_index_oob",
                    f"array index {item_index} out of bounds for length {len(values)}",
                    where=where,
                )
            env[ins["id"]] = values[item_index]
            types[ins["id"]] = types[array_name]["array"]
        elif op == "array.len":
            array_name = ins["args"][0]
            env[ins["id"]] = len(env[array_name])
            types[ins["id"]] = "i64"
        elif op == "record":
            env[ins["id"]] = RecordValue(
                tuple(
                    (field_name, env[source])
                    for field_name, source in sorted(ins["fields"].items())
                )
            )
            types[ins["id"]] = ins["type"]
        elif op == "record.get":
            record_value = env[ins["record"]]
            env[ins["id"]] = record_value.get(ins["field"])
            types[ins["id"]] = types[ins["record"]]["record"][ins["field"]]
        elif op == "print":
            output(_render(env[ins["args"][0]]))
        elif op == "call":
            target = ins["function"]
            result = _execute_function(
                functions=functions,
                function_name=target,
                arguments=[env[name] for name in ins["args"]],
                output=output,
            )
            if result.type != "unit":
                env[ins["id"]] = result.value
                types[ins["id"]] = result.type
        elif op == "if":
            label = "then" if env[ins["cond"]] else "else"
            branch_result = _execute_sequence(
                instructions=ins[label],
                env=dict(env),
                types=dict(types),
                functions=functions,
                function_name=function_name,
                output=output,
                terminator="yield",
                result_type=ins["type"],
                where_prefix=f"{where}.{label}",
            )
            env[ins["id"]] = branch_result.value
            types[ins["id"]] = branch_result.type
        elif op == "repeat":
            count = env[ins["count"]]
            bound = ins["max"]
            if count < 0:
                raise ExecutionError(
                    "apl.repeat_negative_count",
                    "repeat count must be non-negative",
                    where=where,
                )
            if count > bound:
                raise ExecutionError(
                    "apl.repeat_count_exceeds_max",
                    f"repeat count {count} exceeds declared max {bound}",
                    where=where,
                )

            carry_value = env[ins["init"]]
            carry_type = types[ins["init"]]
            for iteration in range(count):
                region_env = dict(env)
                region_types = dict(types)
                region_env[ins["index"]] = iteration
                region_types[ins["index"]] = "i64"
                region_env[ins["carry"]] = carry_value
                region_types[ins["carry"]] = carry_type

                yielded = _execute_sequence(
                    instructions=ins["body"],
                    env=region_env,
                    types=region_types,
                    functions=functions,
                    function_name=function_name,
                    output=output,
                    terminator="yield",
                    result_type=carry_type,
                    where_prefix=f"{where}.body",
                )
                carry_value = yielded.value

            env[ins["id"]] = carry_value
            types[ins["id"]] = carry_type
        else:
            raise ExecutionError(
                "apl.internal_invalid_execution",
                f"unsupported verified op '{op}'",
                where=where,
            )

    raise ExecutionError(
        "apl.internal_invalid_execution",
        f"verified block terminated without {terminator}",
        where=where_prefix,
    )


def _render(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
