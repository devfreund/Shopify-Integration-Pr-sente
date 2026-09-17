"""Sage-Exporter: liest die WKF-Sage per ODBC und schreibt den JSON-Vertrag.

Die Gegenseite ist die Shopify-App unter ``app/``. Der Vertrag steht in
``contract/`` und ist die einzige Schnittstelle zwischen beiden Seiten.

Der Exporter validiert nicht. Geprüft wird ausschließlich in Node
(``app/sync/validate.ts``); zwei Prüfstellen erzeugen zwei Wahrheiten, die
auseinanderlaufen.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
