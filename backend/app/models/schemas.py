"""Modelos Pydantic del dominio: estructura de una factura y resultado de la extracción.

Todos los campos de valor pueden ser `None`: representan campos que el modelo
no pudo extraer con certeza. La interfaz los muestra como "No detectado" en vez
de omitirlos en silencio.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Party(BaseModel):
    name: str | None = None
    tax_id: str | None = None
    address: str | None = None


class InvoiceLine(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    total: float | None = None
    tax_rate: float | None = None


class TaxEntry(BaseModel):
    rate: float | None = None
    amount: float | None = None


class Invoice(BaseModel):
    invoice_number: str | None = None
    issue_date: str | None = None  # normalizada a ISO 8601 (YYYY-MM-DD) o null
    due_date: str | None = None    # normalizada a ISO 8601 (YYYY-MM-DD) o null
    currency: str | None = None
    seller: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)
    lines: list[InvoiceLine] = Field(default_factory=list)
    subtotal: float | None = None
    taxes: list[TaxEntry] = Field(default_factory=list)
    total: float | None = None


class ExtractionResult(BaseModel):
    status: Literal["success", "partial"] = "partial"
    invoice: Invoice = Field(default_factory=Invoice)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_used: str | None = None
