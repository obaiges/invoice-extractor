"""Parseo y normalización de la respuesta del modelo.

El modelo no siempre devuelve JSON perfecto. Este módulo es el encargado de:
- extraer el JSON de una respuesta con ruido (markdown, prosa, ...),
- resolver alias de claves según el idioma del documento,
- normalizar números (formatos EU/US) y fechas (varios formatos) a un valor canónico,
- convertir el JSON crudo en el modelo `Invoice`, listando qué campos faltan y
  detectando anomalías de consistencia (avisos).

Es la última línea de defensa: si aquí no se puede recuperar la información,
el pipeline devuelve un error estructurado en vez de un crash.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from app.models.schemas import Invoice, InvoiceLine, Party, TaxEntry

SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "invoice_number": ("invoice_number", "invoiceNumber", "numero_factura", "numero", "num_factura", "factura"),
    "issue_date": ("issue_date", "issueDate", "fecha_emision", "fecha_emisión", "fecha", "date"),
    "due_date": ("due_date", "dueDate", "vencimiento", "fecha_vencimiento", "fecha_vto"),
    "currency": ("currency", "moneda", "divisa"),
    "subtotal": ("subtotal", "base_imponible", "base", "baseImponible", "subTotal"),
    "total": ("total", "importe_total", "importeTotal", "total_factura"),
    "seller": ("seller", "emisor", "issuer", "vendedor", "proveedor"),
    "buyer": ("buyer", "receptor", "cliente", "customer", "comprador"),
    "lines": ("lines", "items", "line_items", "lineItems", "detalle", "conceptos"),
    "taxes": ("taxes", "tax", "vat", "iva", "impuestos", "tax_breakdown"),
    "warnings": ("warnings", "avisos", "notas"),
}

PARTY_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "nombre", "razon_social", "razón_social", "company"),
    "tax_id": ("tax_id", "taxId", "nif", "cif", "vat", "vat_number", "vatNumber", "dni"),
    "address": ("address", "direccion", "dirección", "domicilio"),
}

LINE_ALIASES: dict[str, tuple[str, ...]] = {
    "description": ("description", "descripcion", "descripción", "concepto", "name", "detalle"),
    "quantity": ("quantity", "cantidad", "units", "unidades"),
    "unit_price": ("unit_price", "unitPrice", "precio_unitario", "precio", "price", "unit price"),
    "total": ("total", "importe", "amount", "line_total"),
    "tax_rate": ("tax_rate", "taxRate", "iva", "vat", "alicuota"),
}

TAX_ALIASES: dict[str, tuple[str, ...]] = {
    "rate": ("rate", "tipo", "iva", "vat"),
    "amount": ("amount", "importe", "cuota", "base_imponible"),
}

# Campos que la interfaz debe mostrar siempre, se hayan extraído o no.
EXPECTED_FIELDS: tuple[str, ...] = (
    "invoice_number",
    "issue_date",
    "due_date",
    "currency",
    "seller.name",
    "seller.tax_id",
    "seller.address",
    "buyer.name",
    "buyer.tax_id",
    "buyer.address",
    "lines",
    "subtotal",
    "taxes",
    "total",
)


def extract_json_payload(raw: str) -> object | None:
    """Extrae el primer objeto JSON válido de una respuesta con ruido.

    Maneja respuestas que incluyen markdown, prosa o texto antes/después del JSON.
    Devuelve `None` si no encuentra nada parseable.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _pick(data: dict, aliases: tuple[str, ...]) -> object | None:
    """Devuelve el primer valor no nulo de las claves dadas."""
    if not isinstance(data, dict):
        return None
    for key in aliases:
        if key in data and data[key] is not None:
            return data[key]
    return None


def to_float(value: object) -> float | None:
    """Convierte un valor a `float` tolerando formatos de números EU/US y símbolos."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    s = value.strip()
    for token in ("€", "EUR", "$", "USD", "GBP", "£", "%"):
        s = s.replace(token, "")
    s = s.strip()
    if not s:
        return None

    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace(" ", "").replace("\u00a0", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        after = s.rsplit(",", 1)[1]
        if len(after) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        number = float(s)
    except ValueError:
        return None
    return -number if negative else number


def to_iso_date(value: object) -> str | None:
    """Normaliza una fecha a ISO 8601 (YYYY-MM-DD) o devuelve `None`."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return None
    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    # "12 de enero de 2024"
    spanish = re.fullmatch(r"(\d{1,2})\s*de\s+([a-záéíóúñ]+)\s*de\s+(\d{4})", s, re.IGNORECASE)
    if spanish:
        day, month_name, year = spanish.groups()
        month = SPANISH_MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day)).isoformat()
            except ValueError:
                return None

    s = s.split("T")[0]
    s = s.split(" ")[0]
    s = s.replace("/", "-").replace(".", "-")

    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if iso:
        year, month, day = iso.groups()
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return None

    dm = re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{2,4})", s)
    if dm:
        day, month, year = dm.groups()
        if len(year) == 2:
            year = f"20{year}" if int(year) < 50 else f"19{year}"
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return None

    return None


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


# El modelo a veces rellena un campo que no sabe con texto explicativo en vez
# de null (p. ej. "missing_tax_id_goes_to_null_instead_as_per_rules"). Se
# detecta y se descarta para que el campo aparezca como "No detectado".
_PLACEHOLDER_EXACT = {
    "null", "none", "n/a", "n.a.", "n/d", "nd", "na", "-", "--", "---",
    "unknown", "missing", "not found", "not available", "not provided",
    "no disponible", "no encontrado", "no consta", "no aplica",
    "no proporcionado", "desconocido", "sin dato",
}

_PLACEHOLDER_KEYWORDS = (
    "missing", "unknown", "notfound", "notavailable", "notprovided", "null",
    "instead", "rules", "placeholder", "nodisponible", "noencontrado",
    "noconsta", "noaplica", "noproporcionado", "desconocido", "no_se",
)


def _looks_like_placeholder(value: str) -> bool:
    """Devuelve `True` si el valor parece texto de relleno y no un dato real."""
    if not value:
        return False
    lowered = value.strip().lower()
    if lowered in _PLACEHOLDER_EXACT:
        return True
    if any(sep in value for sep in (" ", "_", "-")):
        compact = re.sub(r"[^a-z0-9]", "", lowered)
        return any(word in compact for word in _PLACEHOLDER_KEYWORDS)
    return False


def _clean_tax_id(value: object) -> str | None:
    """Limpia un NIF/CIF/VAT y descarta valores placeholder."""
    cleaned = _clean_str(value)
    if cleaned is None or _looks_like_placeholder(cleaned):
        return None
    return cleaned


def _parse_party(raw: object) -> Party:
    if not isinstance(raw, dict):
        return Party()
    return Party(
        name=_clean_str(_pick(raw, PARTY_ALIASES["name"])),
        tax_id=_clean_tax_id(_pick(raw, PARTY_ALIASES["tax_id"])),
        address=_clean_str(_pick(raw, PARTY_ALIASES["address"])),
    )


def _parse_lines(raw: object) -> list[InvoiceLine]:
    if not isinstance(raw, list):
        return []
    lines: list[InvoiceLine] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        lines.append(
            InvoiceLine(
                description=_clean_str(_pick(item, LINE_ALIASES["description"])),
                quantity=to_float(_pick(item, LINE_ALIASES["quantity"])),
                unit_price=to_float(_pick(item, LINE_ALIASES["unit_price"])),
                total=to_float(_pick(item, LINE_ALIASES["total"])),
                tax_rate=to_float(_pick(item, LINE_ALIASES["tax_rate"])),
            )
        )
    return lines


def _parse_taxes(raw: object) -> list[TaxEntry]:
    if not isinstance(raw, list):
        return []
    taxes: list[TaxEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        taxes.append(
            TaxEntry(
                rate=to_float(_pick(item, TAX_ALIASES["rate"])),
                amount=to_float(_pick(item, TAX_ALIASES["amount"])),
            )
        )
    return taxes


def build_invoice(payload: object) -> tuple[Invoice, list[str], list[str]]:
    """Convierte el JSON crudo del modelo en un `Invoice` normalizado.

    Returns:
        Tupla (invoice, missing_fields, warnings). `missing_fields` lista los
        campos esperados que no se han podido extraer.
    """
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return Invoice(), list(EXPECTED_FIELDS), ["La respuesta del modelo no era un objeto JSON válido."]

    for label, raw in (
        ("emisor", _pick(payload, KEY_ALIASES["seller"])),
        ("receptor", _pick(payload, KEY_ALIASES["buyer"])),
    ):
        if isinstance(raw, dict):
            raw_tax_id = _pick(raw, PARTY_ALIASES["tax_id"])
            if _clean_str(raw_tax_id) is not None and _looks_like_placeholder(_clean_str(raw_tax_id)):
                warnings.append(
                    f"El NIF/CIF del {label} no se pudo extraer con certeza; el valor devuelto "
                    "por el modelo era un texto de relleno y se descartó."
                )

    invoice = Invoice(
        invoice_number=_clean_str(_pick(payload, KEY_ALIASES["invoice_number"])),
        issue_date=to_iso_date(_pick(payload, KEY_ALIASES["issue_date"])),
        due_date=to_iso_date(_pick(payload, KEY_ALIASES["due_date"])),
        currency=_clean_str(_pick(payload, KEY_ALIASES["currency"])),
        seller=_parse_party(_pick(payload, KEY_ALIASES["seller"])),
        buyer=_parse_party(_pick(payload, KEY_ALIASES["buyer"])),
        lines=_parse_lines(_pick(payload, KEY_ALIASES["lines"])),
        subtotal=to_float(_pick(payload, KEY_ALIASES["subtotal"])),
        taxes=_parse_taxes(_pick(payload, KEY_ALIASES["taxes"])),
        total=to_float(_pick(payload, KEY_ALIASES["total"])),
    )

    if invoice.currency:
        invoice.currency = invoice.currency.upper()

    missing_fields = _compute_missing_fields(invoice)
    warnings.extend(_check_consistency(invoice))

    model_warnings = _pick(payload, KEY_ALIASES["warnings"])
    if isinstance(model_warnings, list):
        for warning in model_warnings:
            text = _clean_str(warning)
            if text:
                warnings.append(text)

    return invoice, missing_fields, warnings


def _compute_missing_fields(invoice: Invoice) -> list[str]:
    missing: list[str] = []
    if invoice.invoice_number is None:
        missing.append("invoice_number")
    if invoice.issue_date is None:
        missing.append("issue_date")
    if invoice.due_date is None:
        missing.append("due_date")
    if invoice.currency is None:
        missing.append("currency")
    if invoice.seller.name is None:
        missing.append("seller.name")
    if invoice.seller.tax_id is None:
        missing.append("seller.tax_id")
    if invoice.seller.address is None:
        missing.append("seller.address")
    if invoice.buyer.name is None:
        missing.append("buyer.name")
    if invoice.buyer.tax_id is None:
        missing.append("buyer.tax_id")
    if invoice.buyer.address is None:
        missing.append("buyer.address")
    if not invoice.lines:
        missing.append("lines")
    if invoice.subtotal is None:
        missing.append("subtotal")
    if not invoice.taxes:
        missing.append("taxes")
    if invoice.total is None:
        missing.append("total")
    return missing


def _check_consistency(invoice: Invoice) -> list[str]:
    """Detecta incoherencias aritméticas entre líneas, subtotal, impuestos y total."""
    warnings: list[str] = []

    subtotal = invoice.subtotal
    total = invoice.total
    taxes = invoice.taxes

    lines_total = sum(line.total for line in invoice.lines if line.total is not None)
    if invoice.lines and subtotal is not None and any(line.total is not None for line in invoice.lines):
        vat_amounts = [t.amount for t in taxes if t.amount is not None]
        vat_total = sum(vat_amounts) if vat_amounts else 0.0
        gross_total = subtotal + vat_total
        # Las líneas pueden venir con IVA incluido (importe bruto) o sin él (base).
        # Solo se avisa si la suma no cuadra con ninguna de las dos interpretaciones.
        if abs(lines_total - subtotal) > 0.02 and abs(lines_total - gross_total) > 0.02:
            warnings.append(
                f"La suma de las líneas ({lines_total:.2f}) no coincide con la base imponible ({subtotal:.2f})."
            )

    if subtotal is not None and taxes and all(t.amount is not None for t in taxes):
        if abs(subtotal + sum(t.amount for t in taxes) - (total if total is not None else subtotal + sum(t.amount for t in taxes))) > 0.02:
            warnings.append("El importe de impuestos no es consistente con la base imponible y el total.")

    if subtotal is not None and taxes and all(t.rate is not None for t in taxes):
        for tax in taxes:
            if tax.amount is None:
                continue
            expected = subtotal * tax.rate / 100.0
            if abs(expected - tax.amount) > 0.02:
                warnings.append(
                    f"El impuesto al {tax.rate:.2f}% no coincide con su importe "
                    f"(esperado {expected:.2f}, extraído {tax.amount:.2f})."
                )

    if invoice.invoice_number is None and invoice.total is not None:
        warnings.append("No se pudo confirmar el número de factura.")

    return warnings
