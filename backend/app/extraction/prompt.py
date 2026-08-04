"""Prompt y esquema JSON que se envían al modelo de lenguaje.

El esquema también se pasa como `response_schema` (generación controlada de
JSON), así que las claves que usa el modelo son exactamente las que entiende
`app.extraction.parser`. Todos los campos son opcionales y el modelo debe
devolver `null` cuando no pueda determinar un valor con certeza.
"""

from __future__ import annotations

EXTRACTION_PROMPT = """Eres un extractor de datos de facturas. Recibirás una o varias imágenes de un documento de tipo factura (en español o inglés).

Extrae la información siguiendo EXACTAMENTE el esquema JSON indicado. Reglas:
- Devuelve ÚNICAMENTE JSON válido, sin texto adicional, sin markdown.
- Un campo que NO puedas determinar con certeza debe ir a null. Nunca inventes datos.
- NUNCA sustituyas `null` por textos de relleno como "missing", "no disponible", "as per rules" o frases explicativas. Si no ves el NIF/CIF/VAT claramente escrito, devuelve `null`.
- Fechas: formato ISO 8601 (YYYY-MM-DD).
- Cantidades y precios: números (sin símbolos de moneda ni separadores de miles). Si aparece "1.234,56" es 1234.56.
- Moneda: código ISO 4217 (EUR, USD, GBP, ...). Si no se indica, usa la moneda habitual de la factura; si es ambiguo, null.
- Emisor (seller) = quien vende/expide la factura. Receptor (buyer) = quien la recibe.
- En `lines`, cada línea de detalle de la factura (descripción, cantidad, precio unitario e importe). Si una línea tiene IVA, indica su tipo en `tax_rate`.
- En `taxes`, el desglose de impuestos: un elemento por tipo de IVA con su `rate` (%) y `amount` (importe en la moneda de la factura).
- `subtotal` = base imponible. `total` = importe final de la factura.
- En `warnings` indica, en lenguaje natural, cualquier anomalía detectada (p. ej. "El importe de IVA no es consistente con el total"). Si no hay anomalías, devuelve un array vacío.
"""

INVOICE_SCHEMA = {
    "type": "OBJECT",
    "description": "Datos estructurados de una factura.",
    "properties": {
        "invoice_number": {
            "type": "STRING",
            "description": "Número de factura (p. ej. 'INV-2024-001').",
        },
        "issue_date": {
            "type": "STRING",
            "description": "Fecha de emisión en ISO 8601 (YYYY-MM-DD).",
        },
        "due_date": {
            "type": "STRING",
            "description": "Fecha de vencimiento en ISO 8601 (YYYY-MM-DD), si existe.",
        },
        "currency": {
            "type": "STRING",
            "description": "Código de moneda ISO 4217 (EUR, USD, GBP...).",
        },
        "seller": {
            "type": "OBJECT",
            "description": "Emisor de la factura (el que vende).",
            "properties": {
                "name": {"type": "STRING", "description": "Nombre o razón social del emisor."},
                "tax_id": {"type": "STRING", "description": "NIF/CIF/VAT del emisor."},
                "address": {"type": "STRING", "description": "Dirección del emisor."},
            },
        },
        "buyer": {
            "type": "OBJECT",
            "description": "Receptor de la factura (el que compra).",
            "properties": {
                "name": {"type": "STRING", "description": "Nombre o razón social del receptor."},
                "tax_id": {"type": "STRING", "description": "NIF/CIF/VAT del receptor."},
                "address": {"type": "STRING", "description": "Dirección del receptor."},
            },
        },
        "lines": {
            "type": "ARRAY",
            "description": "Líneas de detalle de la factura.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING", "description": "Descripción del concepto."},
                    "quantity": {"type": "NUMBER", "description": "Cantidad/unidades."},
                    "unit_price": {"type": "NUMBER", "description": "Precio unitario sin IVA."},
                    "total": {"type": "NUMBER", "description": "Importe total de la línea."},
                    "tax_rate": {"type": "NUMBER", "description": "Tipo de IVA de la línea (%)."},
                },
            },
        },
        "subtotal": {"type": "NUMBER", "description": "Base imponible."},
        "taxes": {
            "type": "ARRAY",
            "description": "Desglose de impuestos por tipo de IVA.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "rate": {"type": "NUMBER", "description": "Tipo de IVA (%)."},
                    "amount": {"type": "NUMBER", "description": "Importe del impuesto."},
                },
            },
        },
        "total": {"type": "NUMBER", "description": "Importe total de la factura."},
        "warnings": {
            "type": "ARRAY",
            "description": "Anomalías detectadas en la factura.",
            "items": {"type": "STRING"},
        },
    },
}
