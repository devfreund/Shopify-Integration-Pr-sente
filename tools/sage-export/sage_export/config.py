"""Konfiguration: Sage-Verbindung, Exportwurzel, Shop-Zuordnung."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .env import first_env, load_env_files

DEFAULT_CONFIG_NAME = "sage-export.toml"
DEFAULT_EXPORT_ROOT = "export"

#: Umgebungsvariablen je Feld, in Vorrangreihenfolge. Die ``WKF_*``-Namen und
#: ihre ``DB_*``-Fallbacks stammen aus dem Vinsecco-Zugriff auf dieselbe Sage,
#: damit ein Rechner nicht zwei Sätze Zugangsdaten pflegen muss.
ENV_NAMES = {
    "dsn": ("WKF_DSN", "SAGE_EXPORT_DSN"),
    "driver": ("WKF_DRIVER", "DB_DRIVER", "SAGE_EXPORT_DRIVER"),
    "server": ("WKF_SERVER", "DB_SERVER", "SAGE_EXPORT_SERVER"),
    "database": ("WKF_DATABASE", "DB_NAME", "SAGE_EXPORT_DATABASE"),
    "user": ("WKF_UID", "DB_USER", "SAGE_EXPORT_USER"),
    "password": ("WKF_PWD", "DB_PASSWORD", "SAGE_EXPORT_PASSWORD"),
    "mandant": ("WKF_MANDANT", "SAGE_EXPORT_MANDANT"),
    "export_root": ("SAGE_EXPORT_ROOT",),
}

_PASSWORD_ENV = " oder ".join(ENV_NAMES["password"])

#: Windows bringt {SQL Server} mitgeliefert; auf Linux und in der Produktion ist
#: der Microsoft-Treiber 18 üblich. Überschreibbar per WKF_DRIVER.
WINDOWS_DRIVER = "SQL Server"
DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"

#: Ohne das scheitert Treiber 18 an internen Zertifikaten. Wie bei Vinsecco.
DEFAULT_EXTRA = {"TrustServerCertificate": "yes"}


def default_driver() -> str:
    return WINDOWS_DRIVER if sys.platform == "win32" else DEFAULT_DRIVER


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

    @classmethod
    def from_env(cls) -> SageConnection:
        """Verbindung allein aus der Umgebung — das Gegenstück zu Vinseccos
        ``Get_PYODBC_Connection_WKF``.

        Kein Host und kein Passwort im Code. Fehlt etwas, ist das ein Fehler und
        keine stille Vorbelegung: eine halb geratene Verbindung würde entweder
        scheitern oder, schlimmer, auf der falschen Datenbank landen.
        """
        load_env_files(Path.cwd(), _package_root())

        dsn = first_env(*ENV_NAMES["dsn"])
        server = first_env(*ENV_NAMES["server"])
        database = first_env(*ENV_NAMES["database"])
        user = first_env(*ENV_NAMES["user"])
        password = first_env(*ENV_NAMES["password"])
        trusted = _env_flag("WKF_TRUSTED_CONNECTION")

        if not dsn:
            missing = [
                names[0]
                for key, names in (("server", ENV_NAMES["server"]), ("database", ENV_NAMES["database"]))
                if not first_env(*names)
            ]
            if missing:
                raise ConfigError(
                    "Sage-Verbindung unvollständig. Fehlt: "
                    + ", ".join(missing)
                    + ". Entweder WKF_DSN setzen oder WKF_SERVER und WKF_DATABASE "
                    "(Fallback DB_SERVER / DB_NAME). Vorlage: .env.example."
                )

        if not trusted and user and not password:
            raise ConfigError(
                f"Benutzer {user!r} ist gesetzt, aber kein Passwort. {_PASSWORD_ENV} "
                f"in die Umgebung legen, nicht in eine Datei im Repo."
            )
        if not trusted and not user and not dsn:
            raise ConfigError(
                "Keine Anmeldung konfiguriert. Entweder WKF_UID und WKF_PWD "
                "(Fallback DB_USER / DB_PASSWORD) setzen oder "
                "WKF_TRUSTED_CONNECTION=1 für die Windows-Anmeldung."
            )

        return cls(
            dsn=dsn,
            driver=first_env(*ENV_NAMES["driver"]) or default_driver(),
            server=server,
            database=database,
            user=user,
            password=password,
            trusted_connection=trusted,
            extra=dict(DEFAULT_EXTRA),
        )


@dataclass(frozen=True)
class Config:
    sage: SageConnection
    mandant: int
    export_root: Path
    shops: dict[str, str]
    price_lists: dict[str, int] = field(default_factory=dict)
    article_groups: tuple[str, ...] = ()
    evaluation_groups: tuple[int, ...] = ()
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
    # Vor dem Lesen: .env darf die Werte aus der Datei überschreiben, damit
    # Zugangsdaten nie in der versionierten Konfiguration stehen müssen.
    load_env_files(path.parent, Path.cwd())
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

    dsn = _env_or(ENV_NAMES["dsn"], sage_raw.get("dsn"))
    server = _env_or(ENV_NAMES["server"], sage_raw.get("server"))
    database = _env_or(ENV_NAMES["database"], sage_raw.get("database"))
    driver = _env_or(ENV_NAMES["driver"], sage_raw.get("driver"))
    trusted = _env_flag("WKF_TRUSTED_CONNECTION") or bool(
        sage_raw.get("trusted_connection", False)
    )

    if not dsn and not (server and database):
        raise ConfigError(
            f"{path}: [sage] braucht entweder dsn oder server und database "
            f"(auch aus WKF_SERVER / WKF_DATABASE)."
        )
    if not dsn and not driver:
        driver = default_driver()

    password = _env_or(ENV_NAMES["password"], None)
    user = _env_or(ENV_NAMES["user"], sage_raw.get("user"))
    if not trusted and user and not password:
        raise ConfigError(
            f"Benutzer {user!r} ist gesetzt, aber kein Passwort in der Umgebung "
            f"({_PASSWORD_ENV})."
        )

    extra = sage_raw.get("extra", {})
    if not isinstance(extra, dict) or any(
        not isinstance(value, str) for value in extra.values()
    ):
        raise ConfigError(f"{path}: [sage.extra] muss Text auf Text abbilden")
    # Treiber 18 scheitert ohne das an internen Zertifikaten. Ein ausdrücklicher
    # Wert in der Konfiguration gewinnt.
    extra = {**DEFAULT_EXTRA, **extra}

    shops, price_lists = _shops(raw.get("shops"), path)
    mandant = _mandant(sage_raw.get("mandant"), path)

    root = Path(
        _env_or(ENV_NAMES["export_root"], export_raw.get("root")) or DEFAULT_EXPORT_ROOT
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
        price_lists=price_lists,
        article_groups=_article_groups(export_raw.get("article_groups"), path),
        evaluation_groups=_evaluation_groups(export_raw.get("evaluation_groups"), path),
        explode_bom=bool(export_raw.get("explode_bom", False)),
        source=path,
    )


def _section(raw: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: Abschnitt [{name}] fehlt")
    return value


def _mandant(raw: Any, path: Path) -> int:
    value = first_env(*ENV_NAMES["mandant"]) or raw
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


def _article_groups(raw: Any, path: Path) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            f"{path}: [export] article_groups fehlt. Ohne Präsent-Gruppen "
            f"schreibt der Exporter nichts — nicht den ganzen Mandanten."
        )
    groups: list[str] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ConfigError(
                f"{path}: [export] article_groups enthält {item!r}, erwartet Text"
            )
        text = str(item).strip()
        if not text:
            raise ConfigError(f"{path}: [export] article_groups enthält einen leeren Eintrag")
        groups.append(text)
    return tuple(groups)


def _evaluation_groups(raw: Any, path: Path) -> tuple[int, ...]:
    """``USER_Auswertungsgruppe``. Gruppe 800 allein enthält auch Weinpakete."""
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            f"{path}: [export] evaluation_groups fehlt. Artikelgruppe 800 "
            f"enthält Weinpakete; ohne Auswertungsgruppe würde der ganze Mandantenteil mit."
        )
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ConfigError(
                f"{path}: [export] evaluation_groups muss Zahlen enthalten, ist {item!r}"
            )
        values.append(item)
    return tuple(values)


def _shops(raw: Any, path: Path) -> tuple[dict[str, str], dict[str, int]]:
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(
            f"{path}: [shops] fehlt. Ohne Zuordnung Sage-Kennzeichen -> "
            f"myshopify-Domain weiß der Exporter nicht, wohin ein Artikel gehört."
        )

    shops: dict[str, str] = {}
    price_lists: dict[str, int] = {}
    for key, value in raw.items():
        domain, liste_id = _shop_entry(key, value, path)
        shops[key] = domain
        if liste_id is not None:
            price_lists[key] = liste_id
    return shops, price_lists


def _shop_entry(key: str, value: Any, path: Path) -> tuple[str, int | None]:
    liste_id = None
    if isinstance(value, dict):
        domain = value.get("domain")
        if "liste_id" in value and value["liste_id"] is not None:
            liste_id = value["liste_id"]
            if isinstance(liste_id, bool) or not isinstance(liste_id, int):
                raise ConfigError(
                    f"{path}: [shops.{key}] liste_id muss eine Zahl sein, ist {liste_id!r}"
                )
    else:
        domain = value
    if not isinstance(domain, str) or not domain.strip():
        raise ConfigError(f"{path}: [shops] {key!r} braucht eine Domain als Text")
    if not domain.endswith(".myshopify.com"):
        raise ConfigError(
            f"{path}: [shops] {key!r} = {domain!r} ist keine myshopify-Domain. "
            f"Der Verzeichnisname muss der Shop-Domain entsprechen."
        )
    return domain, liste_id


def _env_or(names: tuple[str, ...], fallback: Any) -> str | None:
    """Umgebung vor Konfigurationsdatei, in der Reihenfolge von ``names``."""
    value = first_env(*names)
    if value:
        return value
    if fallback is None:
        return None
    if not isinstance(fallback, str):
        raise ConfigError(f"{names[0]}: erwartet Text, ist {fallback!r}")
    return fallback or None


def _env_flag(name: str) -> bool:
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "ja", "y"}


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent
