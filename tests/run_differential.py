from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from apl.errors import ExecutionError
from apl.host import DeterministicHost
from apl.interpreter import RecordValue, run_program
from apl.lir import lower_program
from apl.optimize import optimize_lir
from apl.wasm import compile_lir_to_wasm


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "differential_manifest.json"
NODE_RUNNER = ROOT / "tests" / "wasm_differential.js"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_value(value: Any, typ: Any) -> Any:
    if typ == "unit":
        return None
    if typ == "bool":
        return bool(value)
    if typ == "string":
        return value
    if typ == "i64":
        return str(value)
    if isinstance(typ, dict):
        if set(typ) == {"range"} or set(typ) == {"quantity"}:
            return str(value)
        if set(typ) == {"array", "len"}:
            return [
                _normalize_value(item, typ["array"])
                for item in value
            ]
        if set(typ) == {"record"}:
            if not isinstance(value, RecordValue):
                raise TypeError(f"expected RecordValue, got {type(value)!r}")
            raw = dict(value.fields)
            return {
                field: _normalize_value(raw[field], field_type)
                for field, field_type in sorted(typ["record"].items())
            }
    raise TypeError(f"unsupported differential value type: {typ!r}")


def _host_from_case(case: dict[str, Any]) -> tuple[DeterministicHost | None, Any]:
    fixture = case.get("host_fixture")
    if fixture is None:
        return None, None
    raw = _load_json(ROOT / fixture)
    return DeterministicHost.from_json_object(raw), raw


def _interpreter_outcome(
    program: dict[str, Any],
    *,
    grants: list[str],
    host: DeterministicHost | None,
) -> dict[str, Any]:
    output: list[str] = []
    try:
        result = run_program(
            program,
            output=output.append,
            capabilities=set(grants),
            host=host,
        )
        return {
            "kind": "return",
            "type": result.type,
            "value": _normalize_value(result.value, result.type),
            "output": output,
        }
    except ExecutionError as exc:
        return {
            "kind": "trap",
            "code": exc.code,
            "output": output,
        }


def main() -> int:
    manifest = _load_json(MANIFEST)
    if not isinstance(manifest, list) or not manifest:
        raise RuntimeError("differential manifest must be a non-empty list")

    seen: set[str] = set()
    plan: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="apl-differential-") as tmp:
        temp = Path(tmp)

        for case in manifest:
            case_id = case["id"]
            if case_id in seen:
                raise RuntimeError(f"duplicate differential case {case_id!r}")
            seen.add(case_id)

            program_path = ROOT / case["file"]
            program = _load_json(program_path)
            grants = list(case.get("grants", []))
            host, host_raw = _host_from_case(case)
            expected = _interpreter_outcome(
                program,
                grants=grants,
                host=host,
            )

            lowered = lower_program(program)
            optimized = optimize_lir(lowered)

            baseline_path = temp / f"{case_id}.baseline.wasm"
            optimized_path = temp / f"{case_id}.optimized.wasm"
            baseline_path.write_bytes(compile_lir_to_wasm(lowered).binary)
            optimized_path.write_bytes(compile_lir_to_wasm(optimized).binary)

            entry_fn = next(
                fn for fn in program["functions"]
                if fn["name"] == program["entry"]
            )
            plan.append({
                "id": case_id,
                "baseline": str(baseline_path),
                "optimized": str(optimized_path),
                "return_type": entry_fn["returns"],
                "grants": grants,
                "host": host_raw,
                "expected": expected,
            })

        plan_path = temp / "plan.json"
        plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

        proc = subprocess.run(
            ["node", str(NODE_RUNNER), str(plan_path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            return proc.returncode

    print(f"differential conformance passed: {len(plan)} cases x baseline/optimized WASM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
