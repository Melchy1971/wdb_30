class DomainError(Exception):
    """Base class for domain and service errors."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class InvalidTransitionError(DomainError):
    """Raised when a status transition is not allowed."""


class ConflictError(DomainError):
    """Raised when an idempotency or uniqueness constraint is violated."""


class ValidationErrorCode:
    SOURCE_INACTIVE = "SOURCE_INACTIVE"
    LOCATION_MISSING = "LOCATION_MISSING"
    LOCATION_NOT_FOUND = "LOCATION_NOT_FOUND"
    LOCATION_NOT_READABLE = "LOCATION_NOT_READABLE"
    LOCATION_UNSUPPORTED_TYPE = "LOCATION_UNSUPPORTED_TYPE"
    LOCATION_EMPTY_UNSUPPORTED = "LOCATION_EMPTY_UNSUPPORTED"


class SourceValidationError(DomainError):
    """Raised when a source cannot be validated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
