from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any

from .canonical import canonical_bytes
from .errors import VerificationError


PRIMITIVE_ID_RE = re.compile(r"p_[0-9a-f]{64}")
PRIMITIVE_SCHEMA = "apl.semantic-primitive.v1"
PRIMITIVE_FUNCTION_PREFIX = "__apl_primitive_"
MAX_PRIMITIVES = 256


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def primitive_payload(raw: Any) -> dict[str, Any]:
    _expect(isinstance(raw, dict), "primitive definition must be an object")
    allowed = {"id", "params", "returns", "body"}
    _expect(
        set(raw) in ({"params", "returns", "body"}, allowed),
        "primitive definition must contain exactly 'params', 'returns', and 'body'"
        " (plus optional 'id')",
    )
    return {
        "params": deepcopy(raw["params"]),
        "returns": deepcopy(raw["returns"]),
        "body": deepcopy(raw["body"]),
    }


def primitive_id(raw: Any) -> str:
    payload = primitive_payload(raw)
    canonical = {
        "schema": PRIMITIVE_SCHEMA,
        **payload,
    }
    return "p_" + hashlib.sha256(canonical_bytes(canonical)).hexdigest()


def primitive_function_name(identifier: str) -> str:
    return PRIMITIVE_FUNCTION_PREFIX + identifier[2:]


def _scan_no_external_calls(instructions: Any, where: str) -> None:
    _expect(isinstance(instructions, list) and bool(instructions),
            f"{where}: primitive body must be a non-empty list")
    for index, ins in enumerate(instructions):
        item_where = f"{where}[{index}]"
        _expect(isinstance(ins, dict), f"{item_where}: instruction must be an object")
        op = ins.get("op")
        _expect(isinstance(op, str), f"{item_where}: missing op")
        _expect(
            op not in {"call", "primitive.call"},
            f"{item_where}: semantic primitive bodies cannot call functions or primitives",
        )
        if op == "if":
            _scan_no_external_calls(ins.get("then"), f"{item_where}.then")
            _scan_no_external_calls(ins.get("else"), f"{item_where}.else")
        elif op == "repeat":
            _scan_no_external_calls(ins.get("body"), f"{item_where}.body")


def _rewrite_calls(
    instructions: list[dict[str, Any]],
    primitive_functions: dict[str, str],
    where: str,
) -> list[dict[str, Any]]:
    rewritten: list[dict[str, Any]] = []
    for index, ins in enumerate(instructions):
        item_where = f"{where}[{index}]"
        node = deepcopy(ins)
        op = node.get("op")

        if op == "primitive.call":
            identifier = node.get("primitive")
            _expect(
                isinstance(identifier, str) and identifier in primitive_functions,
                f"{item_where}: unknown semantic primitive '{identifier}'",
            )
            _expect(
                isinstance(node.get("args"), list),
                f"{item_where}: primitive.call args must be a list",
            )
            replacement: dict[str, Any] = {
                "op": "call",
                "function": primitive_functions[identifier],
                "args": deepcopy(node["args"]),
            }
            if "id" in node:
                replacement["id"] = node["id"]
            if "type" in node:
                replacement["type"] = deepcopy(node["type"])
            rewritten.append(replacement)
            continue

        if op == "if":
            node["then"] = _rewrite_calls(
                node["then"], primitive_functions, f"{item_where}.then"
            )
            node["else"] = _rewrite_calls(
                node["else"], primitive_functions, f"{item_where}.else"
            )
        elif op == "repeat":
            node["body"] = _rewrite_calls(
                node["body"], primitive_functions, f"{item_where}.body"
            )
        rewritten.append(node)
    return rewritten


def lower_primitives(program: dict[str, Any]) -> dict[str, Any]:
    """Lower Draft 0.0.15 semantic primitives to ordinary verified functions."""
    if program.get("apl") != "0.0.15":
        return deepcopy(program)

    raw_primitives = program.get("primitives")
    _expect(isinstance(raw_primitives, list), "primitives must be a list")
    _expect(
        len(raw_primitives) <= MAX_PRIMITIVES,
        f"primitives may contain at most {MAX_PRIMITIVES} definitions",
    )

    by_id: dict[str, dict[str, Any]] = {}
    primitive_functions: dict[str, str] = {}

    for index, primitive in enumerate(raw_primitives):
        where = f"primitives[{index}]"
        _expect(isinstance(primitive, dict), f"{where}: primitive must be an object")
        _expect(
            set(primitive) == {"id", "params", "returns", "body"},
            f"{where}: primitive must contain exactly 'id', 'params', 'returns', and 'body'",
        )
        identifier = primitive.get("id")
        _expect(
            isinstance(identifier, str)
            and PRIMITIVE_ID_RE.fullmatch(identifier) is not None,
            f"{where}: primitive id must match p_[0-9a-f]{{64}}",
        )
        expected = primitive_id(primitive)
        _expect(
            identifier == expected,
            f"{where}: primitive id does not match canonical semantic content; "
            f"expected '{expected}'",
        )
        _expect(identifier not in by_id, f"{where}: duplicate primitive '{identifier}'")
        _scan_no_external_calls(primitive.get("body"), f"{where}.body")
        by_id[identifier] = primitive
        primitive_functions[identifier] = primitive_function_name(identifier)

    functions = program.get("functions")
    _expect(isinstance(functions, list), "functions must be a list")
    for index, fn in enumerate(functions):
        if isinstance(fn, dict):
            name = fn.get("name")
            _expect(
                not (
                    isinstance(name, str)
                    and name.startswith(PRIMITIVE_FUNCTION_PREFIX)
                ),
                f"functions[{index}]: function names beginning with "
                f"'{PRIMITIVE_FUNCTION_PREFIX}' are reserved",
            )

    expanded = deepcopy(program)
    expanded.pop("primitives", None)

    rewritten_functions: list[dict[str, Any]] = []
    for index, fn in enumerate(functions):
        node = deepcopy(fn)
        if isinstance(node, dict) and isinstance(node.get("body"), list):
            node["body"] = _rewrite_calls(
                node["body"],
                primitive_functions,
                f"functions[{index}].body",
            )
        rewritten_functions.append(node)

    generated: list[dict[str, Any]] = []
    for identifier in sorted(by_id):
        primitive = by_id[identifier]
        generated.append({
            "name": primitive_functions[identifier],
            "params": deepcopy(primitive["params"]),
            "returns": deepcopy(primitive["returns"]),
            "effects": [],
            "requires": [],
            "ensures": [],
            "body": deepcopy(primitive["body"]),
        })

    expanded["functions"] = rewritten_functions + generated
    return expanded
