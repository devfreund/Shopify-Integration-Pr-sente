"""Aus Sage-Zeilen werden Shop-Verzeichnisse.

Getrennt in zwei Hälften: ``fetch_rows`` redet mit Sage, ``build_exports``
rechnet. Nur die zweite Hälfte ist ohne Datenbank testbar, deshalb ist die erste
so dünn wie möglich.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import queries
from .bom import group_lines, resolve
from .config import Config
from .model import ChildDocument, Deactivation, SetDocument, ShopExport
from .odbc import Database, Row
from .writer import CHILDREN_DIR, DEACTIVATIONS_FILE, SETS_DIR

_TRUE = {"1", "true", "wahr", "j", "ja", "y", "yes", "x"}
_FALSE = {"0", "false", "falsch", "n", "nein", "no", ""}


@dataclass
class SourceRows:
    children: list[Row] = field(default_factory=list)
    sets: list[Row] = field(default_factory=list)
    bom: list[Row] = field(default_factory=list)


@dataclass
class BuildReport:
    exports: list[ShopExport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def fetch_rows(database: Database, mandant: int) -> SourceRows:
    queries.ensure_ready()
    return SourceRows(
        children=database.rows(queries.CHILDREN_SQL, (mandant,)),
        sets=database.rows(queries.SETS_SQL, (mandant,)),
        bom=database.rows(queries.BOM_SQL, (mandant,)),
    )


def build_exports(rows: SourceRows, config: Config) -> BuildReport:
    report = BuildReport()
    by_parent = group_lines(rows.bom)
    articles = {
        sku: row
        for row in rows.children
        if (sku := _text(row.get("sku")))
    }

    exports: dict[str, ShopExport] = {}
    for row in rows.sets:
        parent_sku = _text(row.get("parent_sku"))
        if not parent_sku:
            continue
        domain = config.domain_for(_text(row.get("shop_key")))
        components = resolve(parent_sku, by_parent, explode=config.explode_bom)
        if not components:
            report.warnings.append(
                f"{domain}: Set {parent_sku} hat keine Stücklistenzeilen in Sage "
                f"und wird nicht exportiert."
            )
            continue
        # Erst hier anlegen: ein Shop ohne verwertbares Set darf nicht als leerer
        # Export erscheinen. Der würde beim Schreiben sein Verzeichnis leeren.
        export = exports.setdefault(domain, ShopExport(domain=domain))
        export.sets.append(
            SetDocument(
                parent_sku=parent_sku,
                title=_text(row.get("title")),
                active=_boolean(row.get("active")),
                components=components,
                html=_optional_text(row.get("html")),
                kennzeichnung_html=_optional_text(row.get("kennzeichnung_html")),
            )
        )

    for export in exports.values():
        export.sets.sort(key=lambda document: document.parent_sku)
        export.children = _children_for(export, articles, report)

    report.exports = [exports[domain] for domain in sorted(exports)]
    return report


def _children_for(
    export: ShopExport,
    articles: dict[str, Row],
    report: BuildReport,
) -> list[ChildDocument]:
    """Nur die Artikel, die in den Stücklisten dieses Shops vorkommen.

    Nicht der ganze Sage-Katalog: die App legt Kinder an, damit die Komponenten
    des Sets auflösbar sind, und nicht um ein Sortiment zu befüllen.

    Eine referenzierte SKU ohne Artikel in Sage wird nicht erfunden. Sie fehlt im
    Export, die App meldet ``missing_child`` und hält den Parent auf Entwurf.
    """
    needed: dict[str, None] = {}
    for document in export.sets:
        for component in document.components:
            needed[component.sku] = None

    children: list[ChildDocument] = []
    for sku in sorted(needed):
        row = articles.get(sku)
        if row is None:
            report.warnings.append(
                f"{export.domain}: Komponente {sku} hat keinen exportierbaren "
                f"Artikel in Sage. Das Set bleibt im Shop ein Entwurf."
            )
            continue
        children.append(
            ChildDocument(
                sku=sku,
                title=_text(row.get("title")),
                active=_boolean(row.get("active")),
                product_type=_optional_text(row.get("product_type")),
                html=_optional_text(row.get("html")),
            )
        )
    return children


def deactivations_for(shop_dir: Path, export: ShopExport) -> list[Deactivation]:
    """Was zuletzt im Export stand und jetzt fehlt.

    Sage liefert kein Ereignis „nicht mehr online", also entsteht es aus dem
    Vergleich mit dem vorigen Export. Einmal gemeldete Deaktivierungen bleiben
    stehen, bis der Artikel zurückkehrt: sonst ginge die Information verloren,
    falls ein Shopify-Lauf dazwischen scheitert. Mehrfaches ``setDraft`` ist
    folgenlos.
    """
    current_sets = {document.parent_sku for document in export.sets}
    current_children = {child.sku for child in export.children}
    current = current_sets | current_children

    pending: dict[str, str] = {}
    for previous in _previous_deactivations(shop_dir / DEACTIVATIONS_FILE):
        pending.setdefault(previous.sku, previous.role)
    for sku in _file_stems(shop_dir / SETS_DIR):
        if sku not in current_sets:
            pending.setdefault(sku, "parent")
    for sku in _file_stems(shop_dir / CHILDREN_DIR):
        if sku not in current_children:
            pending.setdefault(sku, "child")

    return [
        Deactivation(sku=sku, role="parent" if role == "parent" else "child")
        for sku, role in sorted(pending.items())
        if sku not in current
    ]


def _previous_deactivations(path: Path) -> list[Deactivation]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []

    found: list[Deactivation] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        sku = _text(entry.get("sku"))
        if sku:
            role = "parent" if entry.get("role") == "parent" else "child"
            found.append(Deactivation(sku=sku, role=role))
    return found


def _file_stems(directory: Path) -> list[str]:
    try:
        return sorted(path.stem for path in directory.glob("*.json"))
    except OSError:
        return []


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    """HTML unverändert, insbesondere ohne trim. Leer heißt nicht gesetzt."""
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text if text.strip() else None


def _boolean(value: Any) -> Any:
    """Sage-Kennzeichen zu ``true``/``false``.

    Bit, 0/1 und die übliche J/N-Schreibweise werden abgebildet. Alles andere
    geht unverändert durch, damit die Validierung in Node den Wert nennt, statt
    dass hier ein Kennzeichen erraten wird.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    return value


__all__ = [
    "BuildReport",
    "SourceRows",
    "build_exports",
    "deactivations_for",
    "fetch_rows",
]
