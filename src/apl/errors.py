class AplError(Exception):
    """Base error for the APL reference implementation."""


class VerificationError(AplError):
    """Raised when a program is not valid APL IR."""


class ExecutionError(AplError):
    """A deterministic APL execution trap."""

    def __init__(self, code: str, message: str, *, where: str | None = None):
        self.code = code
        self.message = message
        self.where = where
        super().__init__(self.__str__())

    def __str__(self) -> str:
        location = f" {self.where}:" if self.where else ""
        return f"[{self.code}]{location} {self.message}"
