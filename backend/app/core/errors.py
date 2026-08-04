"""Errores de dominio de la aplicación.

Cada error mapea a un código y un status HTTP concreto. Un único handler
(excepciones registradas en `main.py`) los convierte en respuestas JSON
estructuradas, de modo que ningún error llega al cliente como una excepción
sin capturar.
"""

from __future__ import annotations


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class DocumentReadError(AppError):
    status_code = 422
    code = "document_unreadable"


class MissingApiKeyError(AppError):
    status_code = 503
    code = "missing_api_key"


class ExtractionError(AppError):
    status_code = 502
    code = "extraction_failed"
