class AplError(Exception):
    """Base error for the APL reference implementation."""


class VerificationError(AplError):
    """Raised when a program is not valid APL IR."""


class ExecutionError(AplError):
    """Raised when a verified program cannot be executed."""
