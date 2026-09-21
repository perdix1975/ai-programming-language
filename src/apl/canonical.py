from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_text(program: Any) -> str:
    """Return the v0 canonical textual encoding of APL IR."""
    return json.dumps(
        program,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_bytes(program: Any) -> bytes:
    return canonical_text(program).encode("utf-8")


def semantic_hash(program: Any) -> str:
    """Stable SHA-256 identity for the canonical v0 representation."""
    return hashlib.sha256(canonical_bytes(program)).hexdigest()
