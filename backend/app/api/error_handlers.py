from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import ConflictError, InvalidTransitionError, NotFoundError, SourceValidationError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc), "error_code": "NOT_FOUND"})

    @app.exception_handler(InvalidTransitionError)
    async def transition_handler(_: Request, exc: InvalidTransitionError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc), "error_code": "INVALID_STATUS_TRANSITION"},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc), "error_code": "CONFLICT"})

    @app.exception_handler(SourceValidationError)
    async def validation_handler(_: Request, exc: SourceValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.message, "error_code": exc.code})
