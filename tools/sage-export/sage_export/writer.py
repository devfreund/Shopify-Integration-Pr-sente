"""Schreibt ein Shop-Verzeichnis in der Form aus ``contract/README.md``.

    <export-root>/
      <shop>.myshopify.com/
        children/<sku>.json
        sets/<parent_sku>.json
        deactivations.json

Jede Datei wird erst daneben geschrieben und dann an ihren Platz verschoben.
Ein Lauf der App darf nie eine halb geschriebene Datei sehen.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .model import ShopExport

CHILDREN_DIR = "children"
SETS_DIR = "sets"
DEACTIVATIONS_FILE = "deactivations.json"


@dataclass
class WriteReport:
    domain: str
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.domain}: {len(self.written)} geschrieben, "
            f"{len(self.unchanged)} unverändert, {len(self.removed)} entfernt"
        )


def write_export(
    root: Path,
    export: ShopExport,
    *,
    dry_run: bool = False,
    prune: bool = True,
) -> WriteReport:
    shop_dir = root / export.domain
    report = WriteReport(domain=export.domain)

    documents: dict[str, object] = {
        f"{CHILDREN_DIR}/{child.file_name}": child.to_json()
        for child in export.children
    }
    documents.update(
        {
            f"{SETS_DIR}/{document.file_name}": document.to_json()
            for document in export.sets
        }
    )
    documents[DEACTIVATIONS_FILE] = [
        deactivation.to_json() for deactivation in export.deactivations
    ]

    for relative, payload in sorted(documents.items()):
        target = shop_dir / relative
        text = _dump(payload)
        if _current_text(target) == text:
            report.unchanged.append(relative)
            continue
        report.written.append(relative)
        if not dry_run:
            _write_atomic(target, text)

    if prune:
        expected = set(documents)
        for relative in _stale(shop_dir, expected):
            report.removed.append(relative)
            if not dry_run:
                (shop_dir / relative).unlink()

    return report


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _current_text(target: Path) -> str | None:
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _write_atomic(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".tmp")
    staging.write_text(text, encoding="utf-8", newline="\n")
    os.replace(staging, target)


def _stale(shop_dir: Path, expected: set[str]) -> list[str]:
    """JSON-Dateien, die dieser Lauf nicht erzeugt hat.

    Sage hat sie nicht mehr geliefert. Sie stehen zu lassen hieße, der App ein
    Sortiment vorzuspiegeln, das es nicht mehr gibt. Angefasst werden nur
    ``.json``-Dateien in den drei vereinbarten Orten.
    """
    stale: list[str] = []
    for directory in (CHILDREN_DIR, SETS_DIR):
        for existing in sorted((shop_dir / directory).glob("*.json")):
            relative = f"{directory}/{existing.name}"
            if relative not in expected:
                stale.append(relative)
    return stale
