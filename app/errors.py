"""Domain errors, translated to HTTP responses by a single exception handler in
app/main.py so routers/services just raise and don't need per-call try/except."""

from __future__ import annotations


class DomainError(Exception):
    status_code: int = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnauthorizedError(DomainError):
    status_code = 401


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class UnprocessableError(DomainError):
    status_code = 422


class InternalInvariantError(DomainError):
    status_code = 500
