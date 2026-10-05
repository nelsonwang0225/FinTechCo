"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core import config
from app.db.connection import database_exists


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class ApiError(HTTPException):
    """HTTPException carrying a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code


def create_app(db_path: Path | str | None = None) -> FastAPI:
    app = FastAPI(title="FinTechCo Business API", version="1.0.0", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.db_path = Path(db_path) if db_path is not None else config.db_path()

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, str(exc.detail)), headers=exc.headers)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "error")
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path"))
        message = first.get("msg", "Invalid request")
        return JSONResponse(status_code=422, content=error_body("validation_error", f"{where}: {message}" if where else message))

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True, "db": "ok" if database_exists(app.state.db_path) else "missing"}

    from app.api import register_routers

    register_routers(app)
    return app


app = create_app()
