"""Die Sage-Abfragen, analog Vinsecco ``SQL_CoreData_Sets_Complete``.

Vorbild heißt Struktur übernehmen, nicht das Toolkit kopieren und nicht die
Vinsecco-Artikelgruppen 80100/880/800 fest einbacken — der nächste Shop hat
andere Nummernkreise. Artikelgruppen, ``IstVerkaufsartikel``,
``USER_OnlineFTP`` und ``USER_VarianteAktiv`` gehören in die lokale TOML,
nicht in diese Query.

Belegte Spalten (``probe --columns``, nicht geraten):

* ``KHKArtikelStueckliste``: ``Stueckliste`` (Parent), ``Element`` (Kind),
  ``Menge``, ``Sortierung`` (Position).
* ``KHKArtikel``: ``Bezeichnung1`` (Titel), ``Aktiv`` (-1/0, Bool macht die
  Pipeline), ``LangtextHTML`` (Marketing), ``DimensionstextHTML``
  (Kennzeichnung am Parent). Nicht ``Langtext`` / ``LangtextRTF`` / ``Memo``
  und nicht ``Dimensionstext`` ohne HTML.
* Filter am Parent: ``Stuecklistentyp = 1``. Kein SKU-Präfix.

``nutrition_html`` bleibt ``NULL``. ``KHKArtikelVarianten`` hat kein
HTML-Feld; ``USER_JInhalt`` / ``USER_JInhaltRTF`` und die ``USER_NW*``-Zahlen
werden nicht zu HTML gefaltet, nicht gejoint und nicht gelayoutet. RTF geht
nicht in den Shop. ``USER_GastroEmpfehlung`` ebenso nicht.
``price`` ist ``KHKPreislistenArtikel.Einzelpreis`` für die ``liste_id`` aus der TOML.

``shop_key`` und ``product_type`` bleiben ``NULL``. Ein Shop in der TOML
reicht; ``USER_Artikeltyp`` ist ein Kurzcode, nicht Wein/Food/Zubehör.
"""

from __future__ import annotations

import re

PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")

#: Aliase, die jede Abfrage liefern muss.
CHILD_COLUMNS = ("shop_key", "sku", "title", "active", "product_type", "html")
SET_COLUMNS = ("shop_key", "parent_sku", "title", "active", "html", "kennzeichnung_html")
BOM_COLUMNS = ("parent_sku", "sku", "qty", "position", "nutrition_html")
COMPLETE_COLUMNS = (
    "shop_key",
    "parent_sku",
    "title",
    "active",
    "html",
    "kennzeichnung_html",
    "price",
    "sku",
    "child_title",
    "child_active",
    "product_type",
    "child_html",
    "child_price",
    "qty",
    "position",
    "nutrition_html",
)


class QueriesNotConfigured(Exception):
    """Es fehlen noch Sage-Feldnamen."""


#: Spalten von ``KHKArtikelStueckliste``, die in der Architektur-Blaupause
#: festgehalten sind: ``Stueckliste`` ist die Artikelnummer des Parents,
#: ``Element`` die des Kindes, ``Menge`` die Anzahl im Karton.
BOM_PARENT_COLUMN = "stueckliste.Stueckliste"
BOM_CHILD_COLUMN = "stueckliste.Element"
BOM_QTY_COLUMN = "stueckliste.Menge"
BOM_POSITION_COLUMN = "stueckliste.Sortierung"

#: Eine Zeile pro Stücklistenposition, Parent- und Kind-Stammdaten gejoint.
#: Das ist das Gegenstück zu Vinseccos ``SQL_CoreData_Sets_Complete``;
#: ``fetch_rows`` gruppiert danach in Python (ohne pandas).
SETS_COMPLETE_SQL = f"""
SELECT
    CAST(NULL AS nvarchar(64))         AS shop_key,
    parent.Artikelnummer               AS parent_sku,
    parent.Bezeichnung1                AS title,
    parent.Aktiv                       AS active,
    parent.Artikelgruppe               AS article_group,
    parent.USER_Auswertungsgruppe      AS evaluation_group,
    COALESCE(parent.DimensionstextHTML, CAST(parent.Dimensionstext AS nvarchar(max))) AS html,
    COALESCE(parent.DimensionstextHTML, CAST(parent.Dimensionstext AS nvarchar(max))) AS kennzeichnung_html,
    parent_preis.Einzelpreis           AS price,
    {BOM_CHILD_COLUMN}                 AS sku,
    child.Bezeichnung1                 AS child_title,
    child.Aktiv                        AS child_active,
    CAST(NULL AS nvarchar(max))        AS product_type,
    child.LangtextHTML                 AS child_html,
    kind_preis.Einzelpreis             AS child_price,
    variante.USER_NWEnergiekcal        AS brennwert_kcal,
    variante.USER_NWEnergiekj          AS brennwert_kj,
    variante.USER_NWKohlenhydrate      AS kohlenhydrate,
    variante.USER_NWdavonZucker        AS davon_zucker,
    variante.USER_NWFett               AS fett,
    variante.USER_NWgesFettsaeuren     AS davon_gesattigte_fettsauren,
    variante.USER_NWEiweiss            AS eiweis,
    variante.USER_NWSalz               AS salz,
    variante.USER_NWBallaststoffe      AS ballaststoffe,
    variante.USER_JInhalt              AS zutaten,
    variante.USER_JInhaltSpuren        AS allergene,
    variante.USER_JJahrgang            AS jahrgang,
    variante.USER_JAlkGehaltLabel      AS alkohol_vol,
    variante.USER_JCharakteristik      AS charakteristik,
    child.USER_InVerkehrBringer        AS in_verkehr_bringer,
    child.USER_Sulfite                 AS enthalt_sulfite,
    child.USER_Flascheninhalt          AS flascheninhalt,
    child.USER_Land                    AS herkunftsland,
    child.USER_Region                  AS region,
    child.USER_Verkehrsbezeichnung     AS verkehrsbezeichnung,
    {BOM_QTY_COLUMN}                   AS qty,
    {BOM_POSITION_COLUMN}              AS position,
    CAST(NULL AS nvarchar(max))        AS nutrition_html
FROM dbo.KHKArtikelStueckliste AS stueckliste
INNER JOIN dbo.KHKArtikel AS parent
    ON parent.Mandant = stueckliste.Mandant
   AND parent.Artikelnummer = {BOM_PARENT_COLUMN}
INNER JOIN dbo.KHKArtikel AS child
    ON child.Mandant = stueckliste.Mandant
   AND child.Artikelnummer = {BOM_CHILD_COLUMN}
LEFT JOIN dbo.KHKArtikelVarianten AS variante
    ON variante.Mandant = stueckliste.Mandant
   AND variante.Artikelnummer = {BOM_CHILD_COLUMN}
   AND (
        (stueckliste.AuspraegungID <> 0 AND variante.AuspraegungID = stueckliste.AuspraegungID)
        OR (stueckliste.AuspraegungID = 0 AND variante.USER_DefaultArtikel = -1)
   )
LEFT JOIN dbo.KHKPreislistenArtikel AS parent_preis
    ON parent_preis.Mandant = stueckliste.Mandant
   AND parent_preis.Artikelnummer = {BOM_PARENT_COLUMN}
   AND parent_preis.ListeID = ?
   AND parent_preis.AbMenge = 0
   AND parent_preis.AuspraegungID = 0
LEFT JOIN dbo.KHKPreislistenArtikel AS kind_preis
    ON kind_preis.Mandant = stueckliste.Mandant
   AND kind_preis.Artikelnummer = {BOM_CHILD_COLUMN}
   AND kind_preis.ListeID = ?
   AND kind_preis.AbMenge = 0
   AND (
        (stueckliste.AuspraegungID <> 0 AND kind_preis.AuspraegungID = stueckliste.AuspraegungID)
        OR (stueckliste.AuspraegungID = 0 AND kind_preis.AuspraegungID = 0)
   )
WHERE stueckliste.Mandant = ?
  AND parent.Stuecklistentyp = 1
ORDER BY {BOM_PARENT_COLUMN}, {BOM_POSITION_COLUMN}, {BOM_CHILD_COLUMN}
"""

#: Artikel, die als Stücklisten-Element in einem Shop landen können.
CHILDREN_SQL = """
SELECT
    CAST(NULL AS nvarchar(64))      AS shop_key,
    artikel.Artikelnummer           AS sku,
    artikel.Bezeichnung1            AS title,
    artikel.Aktiv                   AS active,
    CAST(NULL AS nvarchar(max))     AS product_type,
    artikel.LangtextHTML            AS html,
    CAST(NULL AS money)             AS price
FROM dbo.KHKArtikel AS artikel
WHERE artikel.Mandant = ?
ORDER BY artikel.Artikelnummer
"""

#: Verkaufbare Präsent-Sets. Erkennung über Stücklistentyp, nie über ein
#: SKU-Präfix. Artikelgruppen gehören in die lokale Konfiguration, nicht hier.
SETS_SQL = """
SELECT
    CAST(NULL AS nvarchar(64))      AS shop_key,
    artikel.Artikelnummer           AS parent_sku,
    artikel.Bezeichnung1            AS title,
    artikel.Aktiv                   AS active,
    artikel.LangtextHTML            AS html,
    artikel.DimensionstextHTML      AS kennzeichnung_html,
    CAST(NULL AS money)             AS price
FROM dbo.KHKArtikel AS artikel
WHERE artikel.Mandant = ?
  AND artikel.Stuecklistentyp = 1
ORDER BY artikel.Artikelnummer
"""

#: Stücklistenzeilen allein. ``nutrition_html`` bleibt NULL: Varianten haben
#: Klartext/RTF und NW-Zahlen, kein HTML. ``Sortierung`` ist die Position.
BOM_SQL = f"""
SELECT
    {BOM_PARENT_COLUMN}             AS parent_sku,
    {BOM_CHILD_COLUMN}              AS sku,
    {BOM_QTY_COLUMN}                AS qty,
    {BOM_POSITION_COLUMN}           AS position,
    CAST(NULL AS nvarchar(max))     AS nutrition_html
FROM dbo.KHKArtikelStueckliste AS stueckliste
WHERE stueckliste.Mandant = ?
ORDER BY {BOM_PARENT_COLUMN}, {BOM_POSITION_COLUMN}, {BOM_CHILD_COLUMN}
"""

ALL_QUERIES = {
    "sets_complete": SETS_COMPLETE_SQL,
    "children": CHILDREN_SQL,
    "sets": SETS_SQL,
    "bom": BOM_SQL,
}

#: Was hinter einem wieder eingefügten Platzhalter zu klären wäre.
OPEN_QUESTIONS = {
    "SHOP_KEY_COLUMN": "Woran hängt in Sage, in welchen Shop ein Artikel gehört?",
    "TITLE_COLUMN": "Welches Feld ist der Shop-Titel (Bezeichnung1, Zusatzbezeichnung, ...)?",
    "ONLINE_FLAG_COLUMN": "Welches Feld ist das Online-Kennzeichen? Muss ein Wahrheitswert werden.",
    "ONLINE_FILTER": "Bedingung für 'gehört in den Shop' — inaktiv/gesperrt gehört heraus.",
    "PRODUCT_TYPE_COLUMN": "Woraus wird product_type (Wein, Food, Zubehör)?",
    "DESCRIPTION_COLUMN": "Welches Feld hält das Marketing-HTML?",
    "KENNZEICHNUNG_COLUMN": "Welches Feld hält den fertigen Kennzeichnungsblock der BOM?",
    "SET_FILTER": "Set-Erkennung über Stücklistentyp und Artikelgruppe, nicht über SKU-Präfix.",
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
