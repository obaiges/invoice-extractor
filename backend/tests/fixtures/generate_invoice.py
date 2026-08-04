"""Generador de facturas PDF sintéticas para los tests.

Se usa únicamente como fixture de pruebas (reportlab), de modo que el pipeline
completo pueda verificarse sin depender de documentos reales ni de una API key.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.pdfgen import canvas

FONT = "Helvetica"


def _draw_complete_invoice(c: canvas.Canvas) -> None:
    c.setFont(FONT, 12)
    c.drawString(50, 800, "ACME SOLUCIONES S.L.")
    c.setFont(FONT, 10)
    c.drawString(50, 784, "CIF: B12345678")
    c.drawString(50, 770, "C/ Inventada 42, 50001 Zaragoza")

    c.setFont(FONT, 16)
    c.drawRightString(545, 800, "FACTURA")
    c.setFont(FONT, 10)
    c.drawRightString(545, 784, "Nº: INV-2024-001")
    c.drawRightString(545, 770, "Fecha: 15/03/2024")
    c.drawRightString(545, 756, "Vencimiento: 15/04/2024")

    c.setFont(FONT, 11)
    c.drawString(50, 720, "Cliente:")
    c.setFont(FONT, 10)
    c.drawString(50, 706, "Comercial Utebo S.L.")
    c.drawString(50, 692, "NIF: A98765432")
    c.drawString(50, 678, "Avda. del Río 8, 50180 Utebo")

    c.setFont(FONT, 10)
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.line(50, 655, 545, 655)
    c.drawString(50, 640, "CONCEPTO")
    c.drawRightString(380, 640, "CANT.")
    c.drawRightString(450, 640, "P.UNIT")
    c.drawRightString(545, 640, "IMPORTE")
    c.line(50, 632, 545, 632)

    lines = [
        ("Consultoria de integracion (60 h)", "3", "300,00", "900,00"),
        ("Licencia anual SaaS", "1", "250,00", "250,00"),
    ]
    y = 616
    for concept, qty, price, total in lines:
        c.drawString(50, y, concept)
        c.drawRightString(380, y, qty)
        c.drawRightString(450, y, price)
        c.drawRightString(545, y, total)
        y -= 16

    c.line(50, y - 4, 545, y - 4)
    y -= 20
    c.drawString(50, y, "Base imponible:")
    c.drawRightString(545, y, "1.150,00")
    y -= 16
    c.drawString(50, y, "IVA 21%:")
    c.drawRightString(545, y, "241,50")
    y -= 16
    c.setFont(FONT + "-Bold", 11)
    c.drawString(50, y, "TOTAL:")
    c.drawRightString(545, y, "1.391,50 EUR")

    c.showPage()
    c.save()


def _draw_incomplete_invoice(c: canvas.Canvas) -> None:
    """Factura con campos ausentes para probar la robustez (estado 'partial')."""
    c.setFont(FONT, 16)
    c.drawRightString(545, 800, "FACTURA")
    c.setFont(FONT, 10)
    c.drawRightString(545, 784, "Fecha: 01/02/2024")

    c.setFont(FONT, 10)
    c.drawString(50, 720, "Cliente: Particular")
    c.line(50, 655, 545, 655)
    c.drawString(50, 640, "CONCEPTO")
    c.drawRightString(380, 640, "CANT.")
    c.drawRightString(450, 640, "P.UNIT")
    c.drawRightString(545, 640, "IMPORTE")
    c.line(50, 632, 545, 632)
    c.drawString(50, 616, "Reparacion de portatil")
    c.drawRightString(380, 616, "1")
    c.drawRightString(450, 616, "90,00")
    c.drawRightString(545, 616, "90,00")

    c.drawString(50, 580, "Total: 90,00")

    c.showPage()
    c.save()


def generate_invoice(variant: str = "complete") -> bytes:
    """Devuelve los bytes de un PDF de factura sintética."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    if variant == "incomplete":
        _draw_incomplete_invoice(c)
    else:
        _draw_complete_invoice(c)
    return buffer.getvalue()
