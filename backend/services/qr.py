"""Render a QR code for a link already validated by its use case."""

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing


def render_qr(url: str) -> str:
    widget = QrCodeWidget(url, barLevel='M')
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(
        256, 256, transform=[256 / (x1 - x0), 0, 0, 256 / (y1 - y0), 0, 0]
    )
    drawing.add(widget)
    return renderSVG.drawToString(drawing)
