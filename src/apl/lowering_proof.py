from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import semantic_hash
from .errors import VerificationError
from .primitives import (
    PRIMITIVE_FUNCTION_PREFIX,
    lower_primitives,
    primitive_function_name,
)
from .verify import verify_program


LOWERING_PROOF_SCHEMA = "apl.lowering-proof.v1"
LOWERING_PROOF_METHOD = "deterministic-replay"


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _collect_call_sites(
    instructions: list[dict[str, Any]],
    *,
    where: str,
    out: list[dict[str, str]],
) -> None:
    for index, ins in enumerate(instructions):
        item_where = f"{where}[{index}]"
        op = ins.get("op")

        if op == "primitive.call":
            identifier = ins["primitive"]
            out.append({
                "path": item_where,
                "primitive": identifier,
                "function": primitive_function_name(identifier),
            })

        if op == "if":
            _collect_call_sites(
                ins["then"],
                where=f"{item_where}.then",
                out=out,
            )
            _collect_call_sites(
                ins["else"],
                where=f"{item_where}.else",
                out=out,
            )
        elif op == "repeat":
            _collect_call_sites(
                ins["body"],
                where=f"{item_where}.body",
                out=out,
            )


def lower_core_program(program: dict[str, Any]) -> dict[str, Any]:
    """Verify source APL and return its deterministic primitive-lowered core."""
    verify_program(program)
    _expect(
        program.get("apl") == "0.0.15",
        "lowering proof certificates require APL 0.0.15",
    )
    return lower_primitives(program)


def build_lowering_proof(program: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic replay-verifiable primitive lowering certificate."""
    core = lower_core_program(program)

    primitives = program["primitives"]
    mappings = [
        {
            "primitive": primitive["id"],
            "function": primitive_function_name(primitive["id"]),
        }
        for primitive in sorted(primitives, key=lambda item: item["id"])
    ]

    call_sites: list[dict[str, str]] = []
    for index, fn in enumerate(program["functions"]):
        _collect_call_sites(
            fn["body"],
            where=f"functions[{index}].body",
            out=call_sites,
        )

    return {
        "schema": LOWERING_PROOF_SCHEMA,
        "method": LOWERING_PROOF_METHOD,
        "source_apl": program["apl"],
        "source_hash": semantic_hash(program),
        "lowered_core_hash": semantic_hash(core),
        "primitive_mappings": mappings,
        "call_sites": call_sites,
    }


def verify_lowering_proof(
    source_program: dict[str, Any],
    lowered_core: dict[str, Any],
    proof: Any,
) -> None:
    """Replay lowering and require exact core/proof agreement."""
    expected_core = lower_core_program(source_program)
    expected_proof = build_lowering_proof(source_program)

    _expect(isinstance(proof, dict), "lowering proof must be an object")
    _expect(
        proof.get("schema") == LOWERING_PROOF_SCHEMA,
        f"unsupported lowering proof schema '{proof.get('schema')}'",
    )
    _expect(
        proof.get("method") == LOWERING_PROOF_METHOD,
        f"unsupported lowering proof method '{proof.get('method')}'",
    )

    _expect(
        lowered_core == expected_core,
        "lowered core artifact does not match deterministic replay",
    )
    _expect(
        proof == expected_proof,
        "lowering proof artifact does not match deterministic replay",
    )

    # Defensive checks make the artifact's intent explicit even though exact
    # equality above already implies them.
    _expect(
        proof["source_hash"] == semantic_hash(source_program),
        "lowering proof source hash mismatch",
    )
    _expect(
        proof["lowered_core_hash"] == semantic_hash(lowered_core),
        "lowering proof core hash mismatch",
    )

    for mapping in proof["primitive_mappings"]:
        _expect(
            mapping["function"].startswith(PRIMITIVE_FUNCTION_PREFIX),
            "lowering proof contains a non-reserved generated function",
        )


def copy_lowered_core(program: dict[str, Any]) -> dict[str, Any]:
    """Return an isolated copy suitable for artifact serialization."""
    return deepcopy(lower_core_program(program))
