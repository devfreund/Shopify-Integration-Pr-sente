"""Die Sage-Abfragen — und die offenen Stellen darin.

**Dieses Modul ist noch nicht lauffähig.** Jede Stelle, an der die Feldnamen der
WKF-Sage noch nicht feststehen, steht als Platzhalter ``{{NAME}}`` im SQL.
``ensure_ready`` bricht ab, solange einer davon offen ist. Ein halb
konfigurierter Exporter darf nicht gegen die Produktivdaten laufen und schon gar
nicht geratene Spalten in einen Händler-Shop schreiben.

Vorgehen zum Schließen der Lücke:

1. ``python -m sage_export probe --tables KHKArtikel`` zeigt die Tabellen.
2. ``python -m sage_export probe --columns KHKArtikel`` zeigt die Spalten.
3. Platzhalter hier ersetzen, ``python -m sage_export check`` bis es still ist.

Vorlage sind die Vinsecco-Abfragen aus ``Create_CoreDataSets_Complete``. Vorlage
heißt lesen und übertragen, nicht das Repo kopieren.

Die **Spaltenaliase** sind dagegen verbindlich: ``pipeline.py`` liest die Zeilen
über diese Namen. Wer sie ändert, ändert beide Seiten.
"""

from __future__ import annotations

import re

PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")

#: Aliase, die jede Abfrage liefern muss.
CHILD_COLUMNS = ("shop_key", "sku", "title", "active", "product_type", "html")
SET_COLUMNS = ("shop_key", "parent_sku", "title", "active", "html", "kennzeichnung_html")
BOM_COLUMNS = ("parent_sku", "sku", "qty", "position", "nutrition_html")


class QueriesNotConfigured(Exception):
    """Es fehlen noch Sage-Feldnamen."""


#: Artikel, die als Stücklisten-Element in einem Shop landen können.
CHILDREN_SQL = """
SELECT
    {{SHOP_KEY_COLUMN}}       AS shop_key,
    artikel.Artikelnummer     AS sku,
    {{TITLE_COLUMN}}          AS title,
    {{ONLINE_FLAG_COLUMN}}    AS active,
    {{PRODUCT_TYPE_COLUMN}}   AS product_type,
    {{DESCRIPTION_COLUMN}}    AS html
FROM dbo.KHKArtikel AS artikel
WHERE artikel.Mandant = ?
  AND {{ONLINE_FILTER}}
ORDER BY artikel.Artikelnummer
"""

#: Verkaufbare Präsent-Sets. Erkennung über Stücklistentyp und Artikelgruppe,
#: nie über ein SKU-Präfix.
SETS_SQL = """
SELECT
    {{SHOP_KEY_COLUMN}}          AS shop_key,
    artikel.Artikelnummer        AS parent_sku,
    {{TITLE_COLUMN}}             AS title,
    {{ONLINE_FLAG_COLUMN}}       AS active,
    {{DESCRIPTION_COLUMN}}       AS html,
    {{KENNZEICHNUNG_COLUMN}}     AS kennzeichnung_html
FROM dbo.KHKArtikel AS artikel
WHERE artikel.Mandant = ?
  AND {{SET_FILTER}}
  AND {{ONLINE_FILTER}}
ORDER BY artikel.Artikelnummer
"""

#: Stücklistenzeilen. ``position`` bestimmt die Reihenfolge im Shop; sie ist
#: Lieferreihenfolge aus Sage, kein Layout der App.
BOM_SQL = """
SELECT
    stueckliste.Artikelnummer          AS parent_sku,
    {{BOM_CHILD_COLUMN}}               AS sku,
    {{BOM_QTY_COLUMN}}                 AS qty,
    {{BOM_POSITION_COLUMN}}            AS position,
    {{BOM_NUTRITION_COLUMN}}           AS nutrition_html
FROM dbo.KHKArtikelStueckliste AS stueckliste
WHERE stueckliste.Mandant = ?
ORDER BY stueckliste.Artikelnummer, {{BOM_POSITION_COLUMN}}
"""

ALL_QUERIES = {
    "children": CHILDREN_SQL,
    "sets": SETS_SQL,
    "bom": BOM_SQL,
}

#: Was hinter jedem Platzhalter zu klären ist. Steht als Klartext im
#: ``check``-Befehl, damit die offene Liste nicht nur im Plan lebt.
OPEN_QUESTIONS = {
    "SHOP_KEY_COLUMN": "Woran hängt in Sage, in welchen Shop ein Artikel gehört?",
    "TITLE_COLUMN": "Welches Feld ist der Shop-Titel (Bezeichnung1, Zusatzbezeichnung, ...)?",
    "ONLINE_FLAG_COLUMN": "Welches Feld ist das Online-Kennzeichen? Muss ein Wahrheitswert werden.",
    "ONLINE_FILTER": "Bedingung für 'gehört in den Shop' — inaktiv/gesperrt gehört heraus.",
    "PRODUCT_TYPE_COLUMN": "Woraus wird product_type (Wein, Food, Zubehör)?",
    "DESCRIPTION_COLUMN": "Welches Feld hält das Marketing-HTML?",
    "KENNZEICHNUNG_COLUMN": "Welches Feld hält den fertigen Kennzeichnungsblock der BOM?",
    "SET_FILTER": "Set-Erkennung über Stücklistentyp und Artikelgruppe, nicht über SKU-Präfix.",
    "BOM_CHILD_COLUMN": "Spalte der Element-Artikelnummer in KHKArtikelStueckliste.",
    "BOM_QTY_COLUMN": "Spalte der Menge. Muss als Zahl herauskommen, nicht als Text.",
    "BOM_POSITION_COLUMN": "Spalte der Positionsnummer für die Reihenfolge.",
    "BOM_NUTRITION_COLUMN": "Nur falls Sage zeilenweise kennzeichnet. Sonst NULL liefern.",
}


def unresolved(sql: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in PLACEHOLDER.finditer(sql):
        seen[match.group(1)] = None
    return list(seen)


def open_placeholders() -> dict[str, list[str]]:
    """Offene Platzhalter je Abfrage, leere Einträge weggelassen."""
    return {
        name: found
        for name, sql in ALL_QUERIES.items()
        if (found := unresolved(sql))
    }


def ensure_ready() -> None:
    open_items = open_placeholders()
    if not open_items:
        return

    lines = ["Die Sage-Abfragen sind unvollständig. Offen:"]
    for query, names in open_items.items():
        lines.append(f"  {query}:")
        for name in names:
            lines.append(f"    {name} — {OPEN_QUESTIONS.get(name, 'ungeklärt')}")
    lines.append("Zu füllen in tools/sage-export/sage_export/queries.py.")
    raise QueriesNotConfigured("\n".join(lines))
