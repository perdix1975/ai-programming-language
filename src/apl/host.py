from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class DeterministicHost:
    """Immutable fixture-backed host resources for deterministic APL execution."""

    files: Mapping[str, str]
    network: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))
        object.__setattr__(self, "network", MappingProxyType(dict(self.network)))

    @classmethod
    def from_json_object(cls, raw: Any) -> "DeterministicHost":
        if not isinstance(raw, dict):
            raise ValueError("host fixture root must be an object")

        files = raw.get("files", {})
        network = raw.get("network", {})
        if not isinstance(files, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in files.items()
        ):
            raise ValueError("host fixture 'files' must map strings to strings")
        if not isinstance(network, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in network.items()
        ):
            raise ValueError("host fixture 'network' must map strings to strings")

        extra = set(raw) - {"files", "network"}
        if extra:
            raise ValueError(f"host fixture has unsupported keys: {sorted(extra)}")
        return cls(files=files, network=network)

    def read_text(self, path: str) -> str | None:
        return self.files.get(path)

    def get_text(self, url: str) -> str | None:
        return self.network.get(url)
