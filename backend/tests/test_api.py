"""Tests del endpoint con el proveedor de extracción mockeado.

Verifican el pipeline completo (validación de archivo → conversión PDF → 
extracción → normalización) sin depender de la API de Gemini real.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.extraction.base import ExtractionProvider
from app.main import create_app
from app.services.document_processor import DocumentProcessor
from tests.fixtures.generate_invoice import generate_invoice


class FakeProvider(ExtractionProvider):
    """Devuelve un JSON fijo simulando la respuesta del modelo."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.received_images: list[bytes] = []

    def extract(self, images: list[bytes], mime_type: str) -> str:
        self.received_images = images
        self.mime_type = mime_type
        return json.dumps(self._payload)


COMPLETE_PAYLOAD = {
    "invoice_number": "INV-2024-001",
    "issue_date": "2024-03-15",
    "due_date": "2024-04-15",
    "currency": "EUR",
    "seller": {"name": "ACME SOLUCIONES S.L.", "tax_id": "B12345678", "address": "C/ Inventada 42"},
    "buyer": {"name": "Comercial Utebo S.L.", "tax_id": "A98765432", "address": "Avda. del Río 8"},
    "lines": [
        {"description": "Consultoria (60 h)", "quantity": 3, "unit_price": 300.0, "total": 900.0, "tax_rate": 21.0},
        {"description": "Licencia SaaS", "quantity": 1, "unit_price": 250.0, "total": 250.0, "tax_rate": 21.0},
    ],
    "subtotal": 1150.0,
    "taxes": [{"rate": 21.0, "amount": 241.5}],
    "total": 1391.5,
    "warnings": [],
}

PARTIAL_PAYLOAD = {
    "invoice_number": None,
    "issue_date": "2024-02-01",
    "due_date": None,
    "currency": None,
    "seller": {"name": None, "tax_id": None, "address": None},
    "buyer": {"name": "Particular", "tax_id": None, "address": None},
    "lines": [{"description": "Reparacion de portatil", "quantity": 1, "unit_price": 90.0, "total": 90.0, "tax_rate": None}],
    "subtotal": 90.0,
    "taxes": [],
    "total": 90.0,
    "warnings": ["No se detectó desglose de IVA."],
}


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture()
def pdf_complete() -> bytes:
    return generate_invoice("complete")


@pytest.fixture()
def pdf_incomplete() -> bytes:
    return generate_invoice("incomplete")


def _override(app: TestClient, payload: dict) -> FakeProvider:
    provider = FakeProvider(payload)
    processor = DocumentProcessor(
        provider=provider,
        max_file_size_bytes=15 * 1024 * 1024,
        max_image_bytes=18 * 1024 * 1024,
    )
    app.app.dependency_overrides[routes.get_processor] = lambda: processor
    return provider


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_complete_invoice(client: TestClient, pdf_complete: bytes):
    provider = _override(client, COMPLETE_PAYLOAD)
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura.pdf", pdf_complete, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["missing_fields"] == []
    assert body["invoice"]["invoice_number"] == "INV-2024-001"
    assert body["invoice"]["total"] == 1391.5
    assert len(body["invoice"]["lines"]) == 2
    assert provider.received_images, "el proveedor debió recibir imágenes renderizadas"
    assert provider.mime_type == "image/png"


def test_extract_partial_invoice(client: TestClient, pdf_incomplete: bytes):
    _override(client, PARTIAL_PAYLOAD)
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura_parcial.pdf", pdf_incomplete, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert "invoice_number" in body["missing_fields"]
    assert "buyer.tax_id" in body["missing_fields"]
    assert body["warnings"]


def test_extract_image(client: TestClient):
    provider = _override(client, COMPLETE_PAYLOAD)
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura.png", b"not a real image", "image/png")},
    )
    # El PNG inválido debe rechazarse antes de llegar al proveedor.
    assert response.status_code == 422
    assert response.json()["code"] == "document_unreadable"
    assert provider.received_images == []


def test_unsupported_extension(client: TestClient):
    _override(client, COMPLETE_PAYLOAD)
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura.txt", b"contenido", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_file"


def test_empty_file(client: TestClient):
    _override(client, COMPLETE_PAYLOAD)
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "document_unreadable"


def test_corrupt_pdf(client: TestClient):
    _override(client, COMPLETE_PAYLOAD)
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura.pdf", b"esto no es un pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "document_unreadable"


def test_missing_api_key_returns_clear_error(client: TestClient, monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "gemini_api_key", None)
    client.app.dependency_overrides.clear()
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("factura.pdf", generate_invoice(), "application/pdf")},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "missing_api_key"
    assert "GEMINI_API_KEY" in body["message"]
