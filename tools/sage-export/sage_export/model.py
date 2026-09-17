"""Die Dokumente des Vertrags als Python-Typen.

Spiegel von ``contract/*.schema.json`` und ``app/sync/types.ts``. Wer hier ein
Feld hinzufügt, ändert zuerst ``contract/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

Role = Literal["parent", "child"]

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class Component:
    sku: str
    #: Zahl. Liefert Sage etwas anderes, geht es unverändert durch, damit die
    #: Validierung in Node den echten Wert nennen kann.
    qty: Any
    nutrition_html: str | None = None

    def to_json(self) -> JsonDict:
        document: JsonDict = {"sku": self.sku, "qty": normalize_qty(self.qty)}
        if self.nutrition_html is not None:
            document["nutrition_html"] = self.nutrition_html
        return document


@dataclass(frozen=True)
class ChildDocument:
    sku: str
    title: str
    active: bool
    product_type: str | None = None
    html: str | None = None

    @property
    def file_name(self) -> str:
        return f"{self.sku}.json"

    def to_json(self) -> JsonDict:
        document: JsonDict = {
            "sku": self.sku,
            "title": self.title,
            "active": self.active,
        }
        if self.product_type is not None:
            document["product_type"] = self.product_type
        if self.html is not None:
            document["html"] = self.html
        return document


@dataclass(frozen=True)
class SetDocument:
    parent_sku: str
    title: str
    active: bool
    components: list[Component]
    html: str | None = None
    kennzeichnung_html: str | None = None

    @property
    def file_name(self) -> str:
        return f"{self.parent_sku}.json"

    def to_json(self) -> JsonDict:
        document: JsonDict = {
            "parent_sku": self.parent_sku,
            "title": self.title,
            "active": self.active,
        }
        if self.html is not None:
            document["html"] = self.html
        if self.kennzeichnung_html is not None:
            document["kennzeichnung_html"] = self.kennzeichnung_html
        document["components"] = [component.to_json() for component in self.components]
        return document


@dataclass(frozen=True)
class Deactivation:
    sku: str
    role: Role

    def to_json(self) -> JsonDict:
        return {"sku": self.sku, "role": self.role}


@dataclass
class ShopExport:
    """Alles, was in genau ein Shop-Verzeichnis gehört."""

    domain: str
    children: list[ChildDocument] = field(default_factory=list)
    sets: list[SetDocument] = field(default_factory=list)
    deactivations: list[Deactivation] = field(default_factory=list)


def normalize_qty(value: Any) -> Any:
    """Ganzzahlige Mengen als ``1`` statt ``1.0`` schreiben.

    Sage liefert ``Menge`` als Dezimalzahl. Das ist Formatierung, keine
    Umrechnung: der Wert bleibt gleich. Was keine Zahl ist, geht unverändert
    ins JSON — die Validierung in Node soll den echten Wert melden.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return value
    number = float(value)
    if number.is_integer():
        return int(number)
    return number
