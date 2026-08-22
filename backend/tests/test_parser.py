"""Tests unitarios del parser: limpieza de JSON, normalización y detección de faltantes."""

from __future__ import annotations

from app.extraction.parser import (
    build_invoice,
    extract_json_payload,
    to_float,
    to_iso_date,
)


class TestExtractJsonPayload:
    def test_plain_json(self):
        raw = '{"invoice_number": "INV-1"}'
        assert extract_json_payload(raw) == {"invoice_number": "INV-1"}

    def test_markdown_fence(self):
        raw = '```json\n{"invoice_number": "INV-1"}\n```'
        assert extract_json_payload(raw) == {"invoice_number": "INV-1"}

    def test_prose_surrounding(self):
        raw = 'Aquí tienes los datos:\n{"invoice_number": "INV-1"}\nEspero que sirva.'
        assert extract_json_payload(raw) == {"invoice_number": "INV-1"}

    def test_unparseable_returns_none(self):
        assert extract_json_payload("no hay json aquí") is None
        assert extract_json_payload("") is None
        assert extract_json_payload(None) is None


class TestToFloat:
    def test_numeric_types(self):
        assert to_float(10) == 10.0
        assert to_float(10.5) == 10.5
        assert to_float(True) is None

    def test_eu_format(self):
        assert to_float("1.234,56") == 1234.56
        assert to_float("1.150,00") == 1150.0

    def test_us_format(self):
        assert to_float("1,234.56") == 1234.56
        assert to_float("1150.00") == 1150.0

    def test_currency_symbols(self):
        assert to_float("1.391,50 EUR") == 1391.5
        assert to_float("€ 300,00") == 300.0
        assert to_float("21%") == 21.0

    def test_negative_parentheses(self):
        assert to_float("(12,34)") == -12.34

    def test_invalid(self):
        assert to_float("abc") is None
        assert to_float("") is None
        assert to_float(None) is None


class TestToIsoDate:
    def test_iso_already(self):
        assert to_iso_date("2024-03-15") == "2024-03-15"

    def test_eu_format(self):
        assert to_iso_date("15/03/2024") == "2024-03-15"
        assert to_iso_date("15-03-2024") == "2024-03-15"

    def test_short_year(self):
        assert to_iso_date("15/03/24") == "2024-03-15"

    def test_spanish_words(self):
        assert to_iso_date("12 de enero de 2024") == "2024-01-12"

    def test_invalid(self):
        assert to_iso_date("no es una fecha") is None
        assert to_iso_date(None) is None


class TestBuildInvoice:
    def test_complete_payload(self):
        payload = {
            "invoice_number": "INV-2024-001",
            "issue_date": "2024-03-15",
            "due_date": "2024-04-15",
            "currency": "eur",
            "seller": {"name": "ACME S.L.", "tax_id": "B12345678", "address": "C/ Inventada 42"},
            "buyer": {"name": "Cliente S.L.", "tax_id": "A98765432", "address": "Avda. 8"},
            "lines": [
                {"description": "Servicio", "quantity": 3, "unit_price": 300, "total": 900, "tax_rate": 21},
                {"description": "Licencia", "quantity": 1, "unit_price": 250, "total": 250, "tax_rate": 21},
            ],
            "subtotal": 1150,
            "taxes": [{"rate": 21, "amount": 241.5}],
            "total": 1391.5,
        }
        invoice, missing, warnings = build_invoice(payload)
        assert invoice.invoice_number == "INV-2024-001"
        assert invoice.currency == "EUR"
        assert invoice.issue_date == "2024-03-15"
        assert len(invoice.lines) == 2
        assert invoice.lines[0].quantity == 3.0
        assert invoice.total == 1391.5
        assert missing == []
        assert warnings == []

    def test_spansh_aliases(self):
        payload = {
            "numero_factura": "F-9",
            "fecha": "10/05/2023",
            "emisor": {"nombre": "Proveedor S.A.", "nif": "C99999999"},
            "base": "1.000,00",
            "iva": [{"tipo": "21", "cuota": "210,00"}],
            "total": "1.210,00",
        }
        invoice, missing, _ = build_invoice(payload)
        assert invoice.invoice_number == "F-9"
        assert invoice.issue_date == "2023-05-10"
        assert invoice.seller.name == "Proveedor S.A."
        assert invoice.seller.tax_id == "C99999999"
        assert invoice.subtotal == 1000.0
        assert invoice.taxes[0].rate == 21.0
        assert invoice.total == 1210.0
        assert "invoice_number" not in missing
        assert "buyer.name" in missing

    def test_all_nulls_reports_missing_fields(self):
        invoice, missing, warnings = build_invoice({})
        assert set(missing) == {
            "invoice_number", "issue_date", "due_date", "currency",
            "seller.name", "seller.tax_id", "seller.address",
            "buyer.name", "buyer.tax_id", "buyer.address",
            "lines", "subtotal", "taxes", "total",
        }
        assert warnings == []

    def test_non_dict_payload(self):
        invoice, missing, warnings = build_invoice([1, 2, 3])
        assert warnings
        assert len(missing) == 14

    def test_inconsistent_totals_raise_warning(self):
        payload = {
            "subtotal": 1000,
            "taxes": [{"rate": 21, "amount": 210}],
            "total": 1200,
        }
        _, _, warnings = build_invoice(payload)
        assert any("consistente" in w for w in warnings)

    def test_lines_with_vat_included_no_warning(self):
        payload = {
            "subtotal": 52.07,
            "taxes": [{"rate": 21, "amount": 10.93}],
            "total": 63.00,
            "lines": [{"description": "Artículo", "total": 63.00, "tax_rate": 21}],
        }
        _, _, warnings = build_invoice(payload)
        assert all("no coincide" not in w for w in warnings)

    def test_lines_consistent_with_subtotal_no_warning(self):
        payload = {
            "subtotal": 1000.0,
            "taxes": [{"rate": 21, "amount": 210.0}],
            "total": 1210.0,
            "lines": [{"description": "A", "total": 1000.0}],
        }
        _, _, warnings = build_invoice(payload)
        assert all("no coincide" not in w for w in warnings)

    def test_lines_inconsistent_with_both_warn(self):
        payload = {
            "subtotal": 52.07,
            "taxes": [{"rate": 21, "amount": 10.93}],
            "total": 63.00,
            "lines": [{"description": "Artículo", "total": 999.00, "tax_rate": 21}],
        }
        _, _, warnings = build_invoice(payload)
        assert any("no coincide" in w for w in warnings)

    def test_placeholder_tax_id_discarded_with_warning(self):
        payload = {
            "invoice_number": "F-1",
            "seller": {
                "name": "LEDUNI GLOBAL SL",
                "tax_id": "missing_tax_id_goes_to_null_instead_as_per_rules",
            },
            "total": 63.00,
        }
        invoice, missing, warnings = build_invoice(payload)
        assert invoice.seller.tax_id is None
        assert "seller.tax_id" in missing
        assert any("relleno" in w for w in warnings)


class TestShippingHandling:
    def test_parsed_from_alias_and_consistent_total(self):
        payload = {
            "subtotal": 1000,
            "gastos_envio_y_gestion": 20,
            "taxes": [{"rate": 21, "amount": 214.20}],
            "total": 1234.20,
        }
        invoice, _, warnings = build_invoice(payload)
        assert invoice.shipping_handling == 20.0
        assert all("consistente" not in w for w in warnings)

    def test_shipping_included_in_subtotal_no_warning(self):
        # El envío ya está dentro de la base imponible: ambas lecturas son válidas.
        payload = {
            "subtotal": 1020,
            "shipping_handling": 20,
            "taxes": [{"rate": 21, "amount": 214.20}],
            "total": 1234.20,
        }
        _, _, warnings = build_invoice(payload)
        assert all("consistente" not in w for w in warnings)

    def test_missing_shipping_still_warns_when_totals_mismatch(self):
        payload = {
            "subtotal": 1000,
            "taxes": [{"rate": 21, "amount": 210}],
            "total": 1250,
        }
        _, _, warnings = build_invoice(payload)
        assert any("consistente" in w for w in warnings)

    def test_rate_computed_over_subtotal_plus_shipping_no_warning(self):
        payload = {
            "subtotal": 1000,
            "shipping_handling": 10,
            "taxes": [{"rate": 21, "amount": 212.10}],
            "total": 1222.10,
        }
        _, _, warnings = build_invoice(payload)
        assert all("no coincide" not in w for w in warnings)

    def test_shipping_not_reported_as_missing_field(self):
        invoice, missing, _ = build_invoice({})
        assert invoice.shipping_handling is None
        assert all("shipping" not in field for field in missing)
