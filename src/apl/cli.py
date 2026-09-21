from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .canonical import canonical_text, semantic_hash
from .errors import AplError
from .interpreter import run_program
from .verify import verify_program


def _load(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("APL file root must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(prog="apl", description="APL reference toolchain")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify an APL IR program")
    p_verify.add_argument("file")

    p_run = sub.add_parser("run", help="execute an APL IR program")
    p_run.add_argument("file")

    p_canon = sub.add_parser("canonicalize", help="emit canonical APL IR")
    p_canon.add_argument("file")

    p_hash = sub.add_parser("hash", help="emit canonical SHA-256 identity")
    p_hash.add_argument("file")

    args = parser.parse_args()

    try:
        program = _load(args.file)
        if args.command == "verify":
            verify_program(program)
            print("valid")
        elif args.command == "run":
            result = run_program(program)
            if result.type != "unit":
                print(f"[return {result.type}] {result.value}")
        elif args.command == "canonicalize":
            verify_program(program)
            print(canonical_text(program))
        elif args.command == "hash":
            verify_program(program)
            print(semantic_hash(program))
        return 0
    except (AplError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"APL error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
