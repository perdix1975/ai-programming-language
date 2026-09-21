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


def run_program(
    program: dict[str, Any],
    *,
    output: Callable[[str], None] = print,
) -> ExecutionResult:
    verify_program(program)
    functions = {fn["name"]: fn for fn in program["functions"]}
    fn = functions[program["entry"]]

    if fn["params"]:
        raise ExecutionError("v0 entry functions cannot require parameters")

    env: dict[str, Any] = {}
    types: dict[str, str] = {p["name"]: p["type"] for p in fn["params"]}

    for index, ins in enumerate(fn["body"]):
        op = ins["op"]
        where = f"{fn['name']}[{index}]"

        if op == "const":
            env[ins["id"]] = ins["value"]
            types[ins["id"]] = ins["type"]
        elif op in {"add", "sub", "mul"}:
            a, b = (env[x] for x in ins["args"])
            raw = a + b if op == "add" else a - b if op == "sub" else a * b
            env[ins["id"]] = _i64(raw, where)
            types[ins["id"]] = "i64"
        elif op == "eq":
            a, b = (env[x] for x in ins["args"])
            env[ins["id"]] = a == b
            types[ins["id"]] = "bool"
        elif op == "print":
            value = env[ins["args"][0]]
            if isinstance(value, bool):
                output("true" if value else "false")
            else:
                output(str(value))
        elif op == "return":
            if fn["returns"] == "unit":
                return ExecutionResult(None, "unit")
            name = ins["value"]
            return ExecutionResult(env[name], types[name])
        else:  # verifier should make this unreachable
            raise ExecutionError(f"{where}: unsupported op '{op}'")

    raise ExecutionError("verified program terminated without return")
