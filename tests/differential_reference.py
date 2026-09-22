from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apl.canonical import semantic_hash
from apl.errors import ExecutionError
from apl.host import DeterministicHost
from apl.interpreter import RecordValue, run_program


def _load_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_value(typ: Any, value: Any) -> Any:
    if typ == "unit":
        return None
    if typ == "i64":
        return str(value)
    if typ == "bool":
        return bool(value)
    if typ == "string":
        return value

    if isinstance(typ, dict):
        if "range" in typ or "quantity" in typ:
            return str(value)
        if set(typ) == {"array", "len"}:
            return [
                _normalize_value(typ["array"], item)
                for item in value
            ]
        if set(typ) == {"record"}:
            if not isinstance(value, RecordValue):
                raise TypeError(f"expected RecordValue, got {type(value)!r}")
            return {
                field: _normalize_value(field_type, value.get(field))
                for field, field_type in sorted(typ["record"].items())
            }

    raise TypeError(f"unsupported differential result type: {typ!r}")


def _host_for_case(case: dict[str, Any]) -> DeterministicHost | None:
    if case.get("host_available") is False:
        return None
    fixture = case.get("host_fixture")
    if fixture is None:
        return None
    raw = _load_json(fixture)
    if not isinstance(raw, dict):
        raise TypeError(f"{fixture}: host fixture root must be an object")
    return DeterministicHost.from_json_object(raw)


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    program = _load_json(case["file"])
    if not isinstance(program, dict):
        raise TypeError(f"{case['file']}: program root must be an object")

    output: list[str] = []
    try:
        result = run_program(
            program,
            output=output.append,
            capabilities=set(case.get("grants", [])),
            host=_host_for_case(case),
        )
    except ExecutionError as exc:
        outcome: dict[str, Any] = {
            "status": "trap",
            "code": exc.code,
            "output": output,
        }
        if case.get("diagnostics"):
            outcome["message"] = exc.message
            outcome["where"] = exc.where
    else:
        outcome = {
            "status": "ok",
            "type": result.type,
            "value": _normalize_value(result.type, result.value),
            "output": output,
        }

    return {
        "source_hash": semantic_hash(program),
        "outcome": outcome,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("output")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list):
        raise TypeError("differential manifest must contain a cases list")

    results: dict[str, Any] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("differential case must be an object")
        name = case.get("name")
        if not isinstance(name, str) or not name:
            raise TypeError("differential case name must be non-empty")
        if name in results:
            raise ValueError(f"duplicate differential case {name!r}")
        results[name] = _run_case(case)

    Path(args.output).write_text(
        json.dumps(
            {"cases": results},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
