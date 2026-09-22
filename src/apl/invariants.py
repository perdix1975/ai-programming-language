from __future__ import annotations

import re
from typing import Any


INVARIANT_NAME_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
MAX_INVARIANTS = 128
MAX_INVARIANT_PARAMS = 16
MAX_INVARIANT_MESSAGE_LENGTH = 512


def index_invariants(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, list):
        return {}
    return {
        invariant["name"]: invariant
        for invariant in raw
        if isinstance(invariant, dict) and isinstance(invariant.get("name"), str)
    }
