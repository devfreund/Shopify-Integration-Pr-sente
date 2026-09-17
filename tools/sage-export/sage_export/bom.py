"""Stücklistenzeilen aus Sage in Komponenten des Vertrags.

Die Reihenfolge kommt aus Sage (``position``). Die App baut keine eigene
Sortierung, und dieses Modul auch nicht.

Mengen werden nicht zusammengefasst. Liefert Sage dieselbe Element-SKU zweimal
an einem Set, bleiben beide Zeilen stehen; die Eingangsvalidierung in Node lehnt
den Export dann mit Datei und Feld ab. Hier still zu addieren hieße raten und
würde den Datenfehler in Sage verdecken.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any

from .model import Component
from .odbc import Row

MAX_DEPTH = 10


class BomCycle(Exception):
    """Eine Stückliste enthält sich selbst."""


def group_lines(rows: Iterable[Row]) -> dict[str, list[Component]]:
    """Zeilen nach Parent gruppieren, in Sage-Reihenfolge."""
    ordered: dict[str, list[tuple[Any, int, Component]]] = {}
    for index, row in enumerate(rows):
        parent = _text(row.get("parent_sku"))
        sku = _text(row.get("sku"))
        if not parent or not sku:
            continue
        component = Component(
            sku=sku,
            qty=_number(row.get("qty")),
            nutrition_html=_optional_text(row.get("nutrition_html")),
        )
        ordered.setdefault(parent, []).append((row.get("position"), index, component))

    grouped: dict[str, list[Component]] = {}
    for parent, entries in ordered.items():
        entries.sort(key=lambda entry: (_sort_key(entry[0]), entry[1]))
        grouped[parent] = [entry[2] for entry in entries]
    return grouped


def resolve(
    parent_sku: str,
    by_parent: Mapping[str, Sequence[Component]],
    *,
    explode: bool = False,
) -> list[Component]:
    """Komponenten eines Sets.

    Ohne ``explode`` die direkten Stücklistenzeilen. Mit ``explode`` werden
    Zeilen, die selbst eine Stückliste haben, durch ihre Elemente ersetzt und
    die Mengen multipliziert.
    """
    if not explode:
        return list(by_parent.get(parent_sku, ()))
    return _explode(parent_sku, by_parent, 1.0, (parent_sku,))


def _explode(
    parent_sku: str,
    by_parent: Mapping[str, Sequence[Component]],
    factor: float,
    path: tuple[str, ...],
) -> list[Component]:
    if len(path) > MAX_DEPTH:
        raise BomCycle(
            f"Stückliste tiefer als {MAX_DEPTH} Stufen: {' -> '.join(path)}"
        )

    exploded: list[Component] = []
    for line in by_parent.get(parent_sku, ()):
        quantity = _scale(line.qty, factor)
        nested = by_parent.get(line.sku)
        if not nested:
            exploded.append(
                Component(
                    sku=line.sku,
                    qty=quantity,
                    nutrition_html=line.nutrition_html,
                )
            )
            continue
        if line.sku in path:
            raise BomCycle(f"Stückliste enthält sich selbst: {' -> '.join((*path, line.sku))}")
        exploded.extend(_explode(line.sku, by_parent, quantity, (*path, line.sku)))
    return exploded


def _scale(qty: Any, factor: float) -> Any:
    """Menge einer verschachtelten Zeile hochrechnen, defekte unverändert lassen."""
    if isinstance(qty, bool) or not isinstance(qty, (int, float)):
        return qty
    return qty * factor


def _sort_key(position: Any) -> tuple[int, float]:
    """Fehlende Positionsnummern hinten anstellen, Reihenfolge sonst stabil."""
    if position is None:
        return (1, 0.0)
    try:
        return (0, float(position))
    except (TypeError, ValueError):
        return (1, 0.0)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    """HTML bleibt unangetastet, auch die Leerzeichen. Leer heißt nicht gesetzt."""
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _number(value: Any) -> Any:
    """Menge als Zahl, sonst unverändert.

    Sage liefert ``Menge`` als ``Decimal``. Alles andere ist ein Datenfehler und
    wird nicht in eine Zahl umgedeutet, sondern durchgelassen: die Validierung in
    Node nennt dann Datei, Feld und den tatsächlichen Wert. Ein stilles ``0``
    oder ein geparster Text würde den Fehler in Sage verdecken.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return value
    return value
