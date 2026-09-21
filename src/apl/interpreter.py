from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .errors import ExecutionError
from .verify import verify_program


@dataclass(frozen=True)
class ExecutionResult:
    value: Any
    type: str


def _i64(value: int, where: str) -> int:
    if value < -(2**63) or value > 2**63 - 1:
        raise ExecutionError(f"{where}: signed i64 overflow")
    return value


def _trunc_div(a: int, b: int, where: str) -> int:
    if b == 0:
        raise ExecutionError(f"{where}: division by zero")
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
    types: dict[str, str],
    functions: dict[str, dict[str, Any]],
    function_name: str,
    output: Callable[[str], None],
    terminator: str,
    result_type: str,
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
                raise ExecutionError(f"{where}: repeat count must be non-negative")
            if count > bound:
                raise ExecutionError(
                    f"{where}: repeat count {count} exceeds declared max {bound}"
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
            raise ExecutionError(f"{where}: unsupported op '{op}'")

    raise ExecutionError(f"{where_prefix}: verified block terminated without {terminator}")


def _render(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
