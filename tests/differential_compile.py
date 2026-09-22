from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apl.wasm import compile_program_to_wasm


def _load_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("output_dir")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list):
        raise TypeError("differential manifest must contain a cases list")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    compiled_sources: dict[str, bytes] = {}
    for case in cases:
        name = case["name"]
        source = case["file"]
        if source not in compiled_sources:
            program = _load_json(source)
            if not isinstance(program, dict):
                raise TypeError(f"{source}: program root must be an object")
            compiled_sources[source] = compile_program_to_wasm(program).binary
        (output_dir / f"{name}.wasm").write_bytes(compiled_sources[source])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
