from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .canonical import canonical_text, semantic_hash
from .errors import AplError
from .host import DeterministicHost
from .interpreter import run_program
from .lir import lower_hash, lower_program, verify_lir
from .resources import ResourceLimits
from .verify import verify_program


def _load(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError("APL file root must be an object")
    return value


def _load_host_fixture(path: str | None) -> DeterministicHost | None:
    if path is None:
        return None
    with Path(path).open("r", encoding="utf-8") as f:
        value = json.load(f)
    return DeterministicHost.from_json_object(value)


def _runtime_limits(args: argparse.Namespace) -> ResourceLimits | None:
    values = (args.max_steps, args.max_output_lines, args.max_host_reads)
    if all(value is None for value in values):
        return None
    return ResourceLimits(
        steps=args.max_steps,
        output_lines=args.max_output_lines,
        host_reads=args.max_host_reads,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="apl", description="APL reference toolchain")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify an APL IR program")
    p_verify.add_argument("file")

    p_run = sub.add_parser("run", help="execute an APL IR program")
    p_run.add_argument("file")
    p_run.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="CAPABILITY",
        help="grant one host capability; may be repeated",
    )
    p_run.add_argument(
        "--host-fixture",
        metavar="FILE",
        help="deterministic JSON host fixture for fs.read_text/net.get_text",
    )
    p_run.add_argument("--max-steps", type=int, metavar="N")
    p_run.add_argument("--max-output-lines", type=int, metavar="N")
    p_run.add_argument("--max-host-reads", type=int, metavar="N")

    p_canon = sub.add_parser("canonicalize", help="emit canonical APL IR")
    p_canon.add_argument("file")

    p_hash = sub.add_parser("hash", help="emit canonical SHA-256 identity")
    p_hash.add_argument("file")

    p_lower = sub.add_parser("lower", help="emit normalized compiler LIR")
    p_lower.add_argument("file")

    p_lower_hash = sub.add_parser(
        "lower-hash",
        help="emit canonical SHA-256 identity of normalized compiler LIR",
    )
    p_lower_hash.add_argument("file")

    p_verify_lir = sub.add_parser("verify-lir", help="verify normalized compiler LIR")
    p_verify_lir.add_argument("file")

    args = parser.parse_args()

    try:
        program = _load(args.file)
        if args.command == "verify":
            verify_program(program)
            print("valid")
        elif args.command == "run":
            result = run_program(
                program,
                capabilities=set(args.allow),
                host=_load_host_fixture(args.host_fixture),
                limits=_runtime_limits(args),
            )
            if result.type != "unit":
                print(f"[return {result.type}] {result.value}")
        elif args.command == "canonicalize":
            verify_program(program)
            print(canonical_text(program))
        elif args.command == "hash":
            verify_program(program)
            print(semantic_hash(program))
        elif args.command == "lower":
            print(canonical_text(lower_program(program)))
        elif args.command == "lower-hash":
            print(lower_hash(program))
        elif args.command == "verify-lir":
            verify_lir(program)
            print("valid")
        return 0
    except (AplError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"APL error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
