"""Aus Sage-Zeilen werden Shop-Verzeichnisse.

Getrennt in zwei Hälften: ``fetch_rows`` redet mit Sage, ``build_exports``
rechnet. Nur die zweite Hälfte ist ohne Datenbank testbar, deshalb ist die erste
so dünn wie möglich.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import queries
from .bom import group_lines, resolve
from .config import Config, ConfigError
from .model import ChildDocument, Deactivation, SetDocument, ShopExport
from .odbc import Database, Row
from .writer import CHILDREN_DIR, DEACTIVATIONS_FILE, SETS_DIR

CHILD_FACT_COLUMNS = (
    "brennwert_kcal",
    "brennwert_kj",
    "kohlenhydrate",
    "davon_zucker",
    "fett",
    "davon_gesattigte_fettsauren",
    "eiweis",
    "salz",
    "ballaststoffe",
    "zutaten",
    "allergene",
    "jahrgang",
    "alkohol_vol",
    "charakteristik",
    "in_verkehr_bringer",
    "enthalt_sulfite",
    "flascheninhalt",
    "herkunftsland",
    "region",
    "verkehrsbezeichnung",
)

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


def fetch_rows(database: Database, mandant: int, liste_id: int | None = None) -> SourceRows:
    """Gegenstück zu Vinseccos ``Create_CoreDataSets_Complete``: eine Abfrage,
    danach Gruppierung in Python — ohne pandas und ohne neues Layout.
    """
    queries.ensure_ready()
    # Ohne Liste in der TOML matcht keine Zeile. Kein stiller Standardpreis.
    liste = -1 if liste_id is None else liste_id
    return source_rows_from_complete(
        database.rows(queries.SETS_COMPLETE_SQL, (liste, liste, mandant))
    )


def source_rows_from_complete(complete: list[Row]) -> SourceRows:
    """Explodierte Sets-Complete-Zeilen in die drei Listen der Pipeline.

    Eine Parent-SKU wird ein Set. Kinder und Mengen kommen aus denselben
    Zeilen. Vorhandene HTML-Texte gehen durch; fehlende bleiben weg.
    """
    sets: dict[str, Row] = {}
    children: dict[str, Row] = {}
    bom: list[Row] = []

    for row in complete:
        parent_sku = _text(row.get("parent_sku"))
        sku = _text(row.get("sku"))
        if parent_sku and parent_sku not in sets:
            sets[parent_sku] = {
                "shop_key": row.get("shop_key"),
                "parent_sku": parent_sku,
                "title": row.get("title"),
                "active": row.get("active"),
                "html": row.get("html"),
                "kennzeichnung_html": row.get("kennzeichnung_html"),
                "price": row.get("price"),
                "article_group": row.get("article_group"),
                "evaluation_group": row.get("evaluation_group"),
            }
        if sku and sku not in children:
            children[sku] = {
                "shop_key": row.get("shop_key"),
                "sku": sku,
                "title": row.get("child_title", row.get("title")),
                "active": row.get("child_active", row.get("active")),
                "product_type": row.get("product_type"),
                "html": row.get("child_html"),
                "price": row.get("child_price"),
                **{name: row.get(name) for name in CHILD_FACT_COLUMNS},
            }
        if parent_sku and sku:
            bom.append(
                {
                    "parent_sku": parent_sku,
                    "sku": sku,
                    "qty": row.get("qty"),
                    "position": row.get("position"),
                    "nutrition_html": row.get("nutrition_html"),
                }
            )

    return SourceRows(
        children=list(children.values()),
        sets=list(sets.values()),
        bom=bom,
    )


def build_exports(rows: SourceRows, config: Config) -> BuildReport:
    report = BuildReport()
    by_parent = group_lines(rows.bom)
    articles = {
        sku: row
        for row in rows.children
        if (sku := _text(row.get("sku")))
    }

    if not config.article_groups or not config.evaluation_groups:
        raise ConfigError(
            "article_groups und evaluation_groups fehlen. "
            "Ohne Präsent-Filter wird nichts geschrieben."
        )

    presents = [row for row in rows.sets if _is_present(row, config)]
    domains = sorted(set(config.shops.values()))
    exports: dict[str, ShopExport] = {}
    for domain in domains:
        for row in presents:
            parent_sku = _text(row.get("parent_sku"))
            if not parent_sku:
                continue
            components = resolve(parent_sku, by_parent, explode=config.explode_bom)
            if not components:
                report.warnings.append(
                    f"{domain}: Set {parent_sku} hat keine Stücklistenzeilen in Sage "
                    f"und wird nicht exportiert."
                )
                continue
            export = exports.setdefault(domain, ShopExport(domain=domain))
            export.sets.append(
                SetDocument(
                    parent_sku=parent_sku,
                    title=_text(row.get("title")),
                    active=_boolean(row.get("active")),
                    components=components,
                    html=_optional_text(row.get("html")),
                    kennzeichnung_html=_optional_text(row.get("kennzeichnung_html")),
                    price=_price(row.get("price")),
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
                price=_price(row.get("price")),
                facts=_facts(row),
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


def _is_present(row: Row, config: Config) -> bool:
    """Präsent ist Sortimentsart, keine Shop-Zuordnung. Werte stehen nur in der TOML."""
    group = _text(row.get("article_group"))
    if group not in config.article_groups:
        return False
    raw = row.get("evaluation_group")
    if isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
        return False
    return int(raw) in config.evaluation_groups


def _shop_key(row: Row, config: Config) -> str:
    """Shop-Kennzeichen aus der Zeile oder, bei genau einem Shop, aus der Config.

    Die App filtert nicht nach Domain im Dokument. Fehlt das Kennzeichen in
    Sage und sind mehrere Shops konfiguriert, ist Raten verboten.
    """
    key = _text(row.get("shop_key"))
    if key:
        return key
    if len(config.shops) == 1:
        return next(iter(config.shops))
    raise ConfigError(
        "Die Abfrage liefert kein shop_key, und [shops] hat mehr als einen "
        "Eintrag. Entweder das Sage-Feld in queries.py setzen oder die "
        "Zuordnung auf genau einen Shop beschränken."
    )


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


_FACT_TEXT = {
    "zutaten",
    "allergene",
    "jahrgang",
    "charakteristik",
    "in_verkehr_bringer",
    "herkunftsland",
    "region",
    "verkehrsbezeichnung",
}


def _fact_value(name: str, raw: Any) -> Any:
    if name == "jahrgang":
        return _jahrgang(raw)
    if name == "enthalt_sulfite":
        return None if raw is None else _boolean(raw)
    if name in _FACT_TEXT:
        return _optional_text(raw)
    return _price(raw)


def _jahrgang(value: Any) -> str | None:
    """0, \"0\" und leer sind kein Jahrgang. 2025 bleibt, ohne den Text zu trimmen."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)) and float(value) == 0:
        return None
    text = _optional_text(value)
    if text is None or text.strip() == "0":
        return None
    return text


def _facts(row: Row) -> dict[str, Any]:
    """Nur gesetzte Kind-Felder. Leer und NULL bleiben weg, 0 wird nicht erfunden."""
    facts: dict[str, Any] = {}
    for name in CHILD_FACT_COLUMNS:
        raw = row.get(name)
        value = _fact_value(name, raw)
        if value is None or value == "":
            continue
        facts[name] = value
    return facts


def _price(value: Any) -> Any:
    """Listenpreis unverändert. ``None`` heißt: Feld weglassen, Shop bleibt 0,00."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


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
    "source_rows_from_complete",
]
