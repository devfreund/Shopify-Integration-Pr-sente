"""Kommandozeile: ``check``, ``probe``, ``export``.

``check`` läuft ohne Sage und sagt, was noch fehlt. ``probe`` ist das Werkzeug,
um die offenen Feldnamen im Sage-Schema zu finden. ``export`` schreibt den
JSON-Vertrag.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, queries
from .config import Config, ConfigError, SageConnection, load_config
from .env import load_env_files
from .model import ShopExport
from .odbc import SageUnavailable, connect
from .pipeline import SourceRows, build_exports, deactivations_for, fetch_rows
from .writer import write_export


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except ConfigError as error:
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 1
    except queries.QueriesNotConfigured as error:
        print(error, file=sys.stderr)
        return 1
    except SageUnavailable as error:
        print(f"Sage: {error}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sage-export",
        description="Exportiert Präsent-Sets aus der WKF-Sage als JSON-Vertrag.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--config",
        type=Path,
        help="Pfad zur sage-export.toml (Standard: neben dem Paket oder im Arbeitsverzeichnis)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Konfiguration prüfen und offene Punkte zeigen")
    check.set_defaults(run=_check)

    probe = sub.add_parser("probe", help="Sage-Schema erkunden")
    probe.add_argument("--tables", metavar="MUSTER", help="Tabellen mit diesem Namensteil")
    probe.add_argument("--columns", metavar="TABELLE", help="Spalten einer Tabelle")
    probe.set_defaults(run=_probe)

    export = sub.add_parser("export", help="Shop-Verzeichnisse schreiben")
    export.add_argument(
        "--dry-run",
        action="store_true",
        help="nur berichten, nichts schreiben oder löschen",
    )
    export.add_argument(
        "--shop",
        metavar="DOMAIN",
        help="nur diese myshopify-Domain exportieren",
    )
    export.add_argument(
        "--keep-stale",
        action="store_true",
        help="Dateien behalten, die Sage nicht mehr liefert",
    )
    export.add_argument("--verbose", action="store_true", help="jede Datei nennen")
    export.add_argument(
        "--rows",
        type=Path,
        metavar="DATEI",
        help="Sage-Zeilen aus JSON lesen statt aus der Datenbank "
        "(siehe samples/rows.example.json)",
    )
    export.set_defaults(run=_export)

    return parser


def _check(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    env_files = load_env_files(Path.cwd(), Path(__file__).resolve().parent.parent)
    print(f"Konfiguration: {config.source}")
    if env_files:
        print(f"Umgebung aus:  {', '.join(str(path) for path in env_files)}")
    print(f"Sage:          {config.sage.redacted()}")
    print(f"Mandant:       {config.mandant}")
    print(f"Exportwurzel:  {config.export_root}")
    print(f"Stückliste:    {'explodiert' if config.explode_bom else 'direkte Zeilen'}")
    print(f"Präsent:       Gruppen {', '.join(config.article_groups)}; Auswertung {', '.join(str(value) for value in config.evaluation_groups)}")
    print("Shops:")
    for key, domain in sorted(config.shops.items()):
        print(f"  {key} -> {domain}")

    open_items = queries.open_placeholders()
    if not open_items:
        print("\nAbfragen: vollständig.")
        return 0

    print("\nAbfragen: unvollständig. Offene Sage-Felder:")
    for query, names in open_items.items():
        print(f"  {query}:")
        for name in names:
            print(f"    {name} — {queries.OPEN_QUESTIONS.get(name, 'ungeklärt')}")
    print("\nZu füllen in sage_export/queries.py. Bis dahin schreibt export nichts.")
    return 1


def _probe(args: argparse.Namespace) -> int:
    if not args.tables and not args.columns:
        print("Entweder --tables MUSTER oder --columns TABELLE angeben.", file=sys.stderr)
        return 2

    sage = _sage_for_probe(args.config)
    with connect(sage) as database:
        if args.tables:
            rows = database.tables(args.tables)
            if not rows:
                print(f"Keine Tabelle enthält {args.tables!r}.")
            for row in rows:
                print(f"{row['schema']}.{row['table']}  ({row['type']})")
        if args.columns:
            rows = database.columns(args.columns)
            if not rows:
                print(f"Tabelle {args.columns!r} hat keine sichtbaren Spalten.")
            for row in rows:
                null = "NULL" if row["nullable"] else "NOT NULL"
                print(f"{row['column']:<40} {row['type']}({row['size']}) {null}")
    return 0


def _sage_for_probe(explicit: Path | None) -> SageConnection:
    """Verbindung für ``probe``, notfalls allein aus der Umgebung.

    ``probe`` ist das Werkzeug, mit dem die offenen Feldnamen überhaupt gefunden
    werden. Es muss deshalb schon laufen, bevor eine ``sage-export.toml``
    existiert: eine ``.env`` mit ``WKF_*`` genügt.
    """
    try:
        return load_config(explicit).sage
    except ConfigError as error:
        if explicit is not None:
            raise
        print(f"Hinweis: {error}", file=sys.stderr)
        print("Hinweis: Verbindung wird aus der Umgebung gelesen.", file=sys.stderr)
        return SageConnection.from_env()


def _export(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    if args.rows:
        rows = _rows_from_file(args.rows)
    else:
        # Vor dem Verbindungsaufbau: eine unvollständige Abfrage soll nicht erst
        # die Produktivdatenbank öffnen.
        queries.ensure_ready()
        with connect(config.sage) as database:
            rows = fetch_rows(database, config.mandant, _liste_id(config))

    report = build_exports(rows, config)
    for warning in report.warnings:
        print(f"Hinweis: {warning}", file=sys.stderr)

    exports = report.exports
    if args.shop:
        exports = [export for export in exports if export.domain == args.shop]
        if not exports:
            print(f"Sage liefert nichts für {args.shop}.", file=sys.stderr)
            return 1

    if not exports:
        # Ein leeres Ergebnis ist fast immer ein Abfrage- oder Filterfehler.
        # Darauf hin den vorhandenen Export zu löschen wäre der schlimmste Fall.
        print(
            "Sage liefert kein einziges Set. Es wird nichts geschrieben und "
            "nichts gelöscht.",
            file=sys.stderr,
        )
        return 1

    for skipped in _untouched_shops(config, exports):
        print(
            f"Hinweis: {skipped} hat einen Export, bekommt diesmal aber keine Daten. "
            f"Unverändert gelassen.",
            file=sys.stderr,
        )

    for export in exports:
        export.deactivations = deactivations_for(
            config.export_root / export.domain, export
        )
        written = write_export(
            config.export_root,
            export,
            dry_run=args.dry_run,
            prune=not args.keep_stale,
        )
        print(_line(export, written.summary()))
        if args.verbose:
            for relative in written.written:
                print(f"    + {relative}")
            for relative in written.removed:
                print(f"    - {relative}")

    if args.dry_run:
        print("\nTrockenlauf: keine Datei angefasst.")
    return 0


def _liste_id(config: Config) -> int | None:
    """Eine Preisliste je Lauf. Steht am Shop in der TOML, nie in der Query."""
    ids = set(config.price_lists.values())
    if len(ids) > 1:
        raise ConfigError(
            "Die Shops haben verschiedene liste_id. Ein Export-Lauf kann nur eine Preisliste lesen."
        )
    if len(config.shops) == 1:
        return config.price_lists.get(next(iter(config.shops)))
    return next(iter(ids)) if ids else None


def _rows_from_file(path: Path) -> SourceRows:
    """Sage-Zeilen aus JSON.

    Damit ist die Kette Zeilen -> Dokumente -> Dateien prüfbar, solange die
    Abfragen noch offen sind. Ersetzt keine Sage-Anbindung.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Zeilendatei nicht gefunden: {path}") from None
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: kein gültiges JSON: {error}") from error

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: erwartet ein Objekt mit children, sets und bom")

    sections = {}
    for name in ("children", "sets", "bom"):
        value = raw.get(name, [])
        if not isinstance(value, list):
            raise ConfigError(f"{path}: {name} muss eine Liste sein")
        sections[name] = value
    return SourceRows(**sections)


def _line(export: ShopExport, summary: str) -> str:
    return (
        f"{summary} | {len(export.sets)} Sets, {len(export.children)} Kinder, "
        f"{len(export.deactivations)} Deaktivierungen"
    )


def _untouched_shops(config: Config, exports: list[ShopExport]) -> list[str]:
    handled = {export.domain for export in exports}
    if not config.export_root.is_dir():
        return []
    return sorted(
        path.name
        for path in config.export_root.iterdir()
        if path.is_dir() and path.name not in handled and path.name in set(config.shops.values())
    )
