"""Central registration of ingress exception → HTTP response mapping."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .errors import IngressDetailError


def register_ingress_exception_handlers(app: FastAPI) -> None:
    """Map :class:`IngressDetailError` to the legacy ``{"detail": ...}`` JSON shape."""

    @app.exception_handler(IngressDetailError)
    async def _ingress_detail_handler(
        _request: Request, exc: IngressDetailError
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
