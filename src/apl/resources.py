from __future__ import annotations

from dataclasses import dataclass

from .errors import ExecutionError


RESOURCE_LIMIT_MAXIMA = {
    "steps": 10_000_000,
    "output_lines": 1_000_000,
    "host_reads": 1_000_000,
}


def _validate_optional_limit(name: str, value: int | None) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} limit must be an integer or null")
    maximum = RESOURCE_LIMIT_MAXIMA[name]
    if value < 0 or value > maximum:
        raise ValueError(f"{name} limit must be in [0, {maximum}]")


@dataclass(frozen=True)
class ResourceLimits:
    steps: int | None = None
    output_lines: int | None = None
    host_reads: int | None = None

    def __post_init__(self) -> None:
        _validate_optional_limit("steps", self.steps)
        _validate_optional_limit("output_lines", self.output_lines)
        _validate_optional_limit("host_reads", self.host_reads)

    @classmethod
    def from_program_object(cls, raw: dict[str, int]) -> "ResourceLimits":
        return cls(
            steps=raw["steps"],
            output_lines=raw["output_lines"],
            host_reads=raw["host_reads"],
        )

    def restricted_by(self, host: "ResourceLimits | None") -> "ResourceLimits":
        if host is None:
            return self

        def restrict(program_value: int | None, host_value: int | None) -> int | None:
            if program_value is None:
                return host_value
            if host_value is None:
                return program_value
            return min(program_value, host_value)

        return ResourceLimits(
            steps=restrict(self.steps, host.steps),
            output_lines=restrict(self.output_lines, host.output_lines),
            host_reads=restrict(self.host_reads, host.host_reads),
        )


@dataclass
class ExecutionBudget:
    remaining_steps: int | None
    remaining_output_lines: int | None
    remaining_host_reads: int | None

    @classmethod
    def from_limits(cls, limits: ResourceLimits) -> "ExecutionBudget":
        return cls(
            remaining_steps=limits.steps,
            remaining_output_lines=limits.output_lines,
            remaining_host_reads=limits.host_reads,
        )

    @staticmethod
    def _consume(value: int | None, resource: str, where: str) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ExecutionError(
                "apl.resource_limit",
                f"{resource} resource limit exhausted",
                where=where,
            )
        return value - 1

    def consume_step(self, where: str) -> None:
        self.remaining_steps = self._consume(
            self.remaining_steps, "steps", where
        )

    def consume_output_line(self, where: str) -> None:
        self.remaining_output_lines = self._consume(
            self.remaining_output_lines, "output_lines", where
        )

    def consume_host_read(self, where: str) -> None:
        self.remaining_host_reads = self._consume(
            self.remaining_host_reads, "host_reads", where
        )
