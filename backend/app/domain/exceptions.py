class DomainError(Exception):
    """Base class for domain and service errors."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class InvalidTransitionError(DomainError):
    """Raised when a status transition is not allowed."""


class ConflictError(DomainError):
    """Raised when an idempotency or uniqueness constraint is violated."""
