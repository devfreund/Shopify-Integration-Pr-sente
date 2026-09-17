"""Konfiguration: Sage-Verbindung, Exportwurzel, Shop-Zuordnung."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_NAME = "sage-export.toml"
DEFAULT_EXPORT_ROOT = "export"

_PASSWORD_ENV = "SAGE_EXPORT_PASSWORD"


class ConfigError(Exception):
    """Die Konfiguration ist unbrauchbar. Ohne sie wird nichts exportiert."""


@dataclass(frozen=True)
class SageConnection:
    """Verbindungsdaten der WKF-Sage.

    Entweder ``dsn`` (vorkonfigurierte ODBC-Datenquelle) oder ``driver`` plus
    ``server`` und ``database``. Das Passwort kommt nur aus der Umgebung.
    """

    dsn: str | None = None
    driver: str | None = None
    server: str | None = None
    database: str | None = None
    user: str | None = None
    password: str | None = None
    trusted_connection: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    def connection_string(self) -> str:
        parts: list[str] = []
        if self.dsn:
            parts.append(f"DSN={self.dsn}")
        else:
            parts.append(f"DRIVER={{{self.driver}}}")
            parts.append(f"SERVER={self.server}")
            parts.append(f"DATABASE={self.database}")

        if self.trusted_connection:
            parts.append("Trusted_Connection=yes")
        else:
            if self.user:
                parts.append(f"UID={self.user}")
            if self.password:
                parts.append(f"PWD={self.password}")

        parts.extend(f"{key}={value}" for key, value in self.extra.items())
        return ";".join(parts)

    def redacted(self) -> str:
        if self.password:
            return self.connection_string().replace(self.password, "***")
        return self.connection_string()


@dataclass(frozen=True)
class Config:
    sage: SageConnection
    mandant: int
    export_root: Path
    shops: dict[str, str]
    explode_bom: bool = False
    source: Path | None = None

    def domain_for(self, shop_key: str) -> str:
        """myshopify-Domain für ein Sage-Kennzeichen.

        Ein unbekanntes Kennzeichen bricht ab. Ohne Zuordnung ist unklar, in
        welchen Shop der Artikel gehört — Raten hieße fremdes Sortiment in
        einen Shop schreiben.
        """
        domain = self.shops.get(shop_key)
        if domain is None:
            known = ", ".join(sorted(self.shops)) or "keine"
            raise ConfigError(
                f"Sage-Kennzeichen {shop_key!r} ist keinem Shop zugeordnet "
                f"(bekannt: {known}). [shops] in der Konfiguration ergänzen."
            )
        return domain


def find_config(explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigError(f"Konfiguration nicht gefunden: {explicit}")
        return explicit

    candidate = Path.cwd() / DEFAULT_CONFIG_NAME
    if candidate.is_file():
        return candidate

    beside_package = Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_NAME
    if beside_package.is_file():
        return beside_package

    raise ConfigError(
        f"Keine {DEFAULT_CONFIG_NAME} gefunden. "
        f"Vorlage: {DEFAULT_CONFIG_NAME}.example kopieren und ausfüllen."
    )


def load_config(explicit: Path | None = None) -> Config:
    path = find_config(explicit)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: kein gültiges TOML: {error}") from error

    return _from_mapping(raw, path)


def _from_mapping(raw: dict[str, Any], path: Path) -> Config:
    sage_raw = _section(raw, "sage", path)
    export_raw = raw.get("export", {})
    if not isinstance(export_raw, dict):
        raise ConfigError(f"{path}: [export] muss eine Tabelle sein")

    if "password" in sage_raw:
        raise ConfigError(
            f"{path}: Passwörter gehören nicht in die Konfiguration, "
            f"sondern in die Umgebungsvariable {_PASSWORD_ENV}."
        )

    dsn = _env_or("SAGE_EXPORT_DSN", sage_raw.get("dsn"))
    driver = _env_or("SAGE_EXPORT_DRIVER", sage_raw.get("driver"))
    server = _env_or("SAGE_EXPORT_SERVER", sage_raw.get("server"))
    database = _env_or("SAGE_EXPORT_DATABASE", sage_raw.get("database"))
    trusted = bool(sage_raw.get("trusted_connection", False))

    if not dsn and not (driver and server and database):
        raise ConfigError(
            f"{path}: [sage] braucht entweder dsn oder driver, server und database."
        )

    password = os.environ.get(_PASSWORD_ENV)
    user = _env_or("SAGE_EXPORT_USER", sage_raw.get("user"))
    if not trusted and user and not password:
        raise ConfigError(
            f"Benutzer {user!r} ist gesetzt, aber {_PASSWORD_ENV} fehlt in der Umgebung."
        )

    extra = sage_raw.get("extra", {})
    if not isinstance(extra, dict) or any(
        not isinstance(value, str) for value in extra.values()
    ):
        raise ConfigError(f"{path}: [sage.extra] muss Text auf Text abbilden")

    shops = _shops(raw.get("shops"), path)
    mandant = _mandant(sage_raw.get("mandant"), path)

    root = Path(
        _env_or("SAGE_EXPORT_ROOT", export_raw.get("root")) or DEFAULT_EXPORT_ROOT
    )
    if not root.is_absolute():
        root = (path.parent / root).resolve()

    return Config(
        sage=SageConnection(
            dsn=dsn,
            driver=driver,
            server=server,
            database=database,
            user=user,
            password=password,
            trusted_connection=trusted,
            extra=dict(extra),
        ),
        mandant=mandant,
        export_root=root,
        shops=shops,
        explode_bom=bool(export_raw.get("explode_bom", False)),
        source=path,
    )


def _section(raw: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: Abschnitt [{name}] fehlt")
    return value


def _mandant(raw: Any, path: Path) -> int:
    value = os.environ.get("SAGE_EXPORT_MANDANT", raw)
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            raise ConfigError(f"{path}: mandant muss eine Zahl sein, ist {value!r}") from None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(
            f"{path}: [sage] mandant fehlt. Sage-100-Tabellen filtern über diese Spalte."
        )
    return value


def _shops(raw: Any, path: Path) -> dict[str, str]:
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(
            f"{path}: [shops] fehlt. Ohne Zuordnung Sage-Kennzeichen -> "
            f"myshopify-Domain weiß der Exporter nicht, wohin ein Artikel gehört."
        )

    shops: dict[str, str] = {}
    for key, domain in raw.items():
        if not isinstance(domain, str) or not domain.strip():
            raise ConfigError(f"{path}: [shops] {key!r} braucht eine Domain als Text")
        if not domain.endswith(".myshopify.com"):
            raise ConfigError(
                f"{path}: [shops] {key!r} = {domain!r} ist keine myshopify-Domain. "
                f"Der Verzeichnisname muss der Shop-Domain entsprechen."
            )
        shops[key] = domain
    return shops


def _env_or(name: str, fallback: Any) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if fallback is None:
        return None
    if not isinstance(fallback, str):
        raise ConfigError(f"{name}: erwartet Text, ist {fallback!r}")
    return fallback or None
