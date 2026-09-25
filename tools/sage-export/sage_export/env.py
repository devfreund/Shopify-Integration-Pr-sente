"""``.env`` einlesen, damit Zugangsdaten nicht in Dateien im Repo landen.

Vorbild ist das Vinsecco-Vorgehen: Verbindungsdaten kommen aus der Umgebung,
nicht aus dem Code und nicht aus der versionierten Konfiguration.

``python-dotenv`` wird benutzt, wenn es installiert ist. Fehlt es, greift ein
schmaler eigener Leser — sonst würde ``check`` an einer fehlenden Bibliothek
scheitern, obwohl es gerade sagen soll, was fehlt.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Kandidaten in Suchreihenfolge. Die erste gefundene Datei gewinnt je Schlüssel;
#: bereits gesetzte Umgebungsvariablen werden nie überschrieben.
DEFAULT_NAMES = (".env",)

#: Notbremse für Tests: sonst würde eine echte ``.env`` auf dem Entwicklerrechner
#: in die Testläufe lecken und sie unberechenbar machen.
SKIP_VAR = "SAGE_EXPORT_SKIP_DOTENV"


def load_env_files(*directories: Path) -> list[Path]:
    """``.env`` aus den genannten Verzeichnissen laden.

    Gibt die tatsächlich gelesenen Dateien zurück, damit ``check`` sie nennen
    kann. Vorhandene Umgebungsvariablen haben Vorrang: was in der Shell steht,
    gewinnt gegen die Datei.
    """
    if os.environ.get(SKIP_VAR):
        return []

    loaded: list[Path] = []
    for directory in directories:
        for name in DEFAULT_NAMES:
            path = directory / name
            if not path.is_file():
                continue
            _load_file(path)
            loaded.append(path)
    return loaded


def _load_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_minimal(path)
        return
    load_dotenv(path, override=False)


def _load_minimal(path: Path) -> None:
    """Ersatz für python-dotenv: ``KEY=VALUE``, Kommentare, einfache Anführung."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def first_env(*names: str) -> str | None:
    """Erster gesetzter, nicht leerer Wert aus mehreren Namen.

    Damit lassen sich die Vinsecco-Namen (``WKF_*``) und ihre Fallbacks
    (``DB_*``) in einer festen Reihenfolge abfragen.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


__all__ = ["first_env", "load_env_files"]
