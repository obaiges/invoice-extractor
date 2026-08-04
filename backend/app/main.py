"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Zebra Invoice Extractor API",
        description="Extracción estructurada de facturas (PDF/imagen) usando Gemini.",
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router)

    @application.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("AppError %s (%s): %s", exc.code, request.url.path, exc)
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "code": exc.code, "message": str(exc)},
        )

    @application.exception_handler(Exception)
    async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error inesperado en %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "internal_error",
                "message": "Ocurrió un error inesperado en el servidor. Inténtalo de nuevo.",
            },
        )

    return application


app = create_app()
