"""ODBC-Zugriff auf die WKF-Sage. Lesend, nie schreibend.

``pyodbc`` wird erst beim Verbinden importiert. So laufen Tests, ``--help`` und
``check`` auf einem Rechner ohne ODBC-Treiber.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from .config import SageConnection

Row = dict[str, Any]


class SageUnavailable(Exception):
    """Verbindung oder Abfrage ist gescheitert."""


class Database(Protocol):
    """Was der Exporter von einer Datenquelle braucht.

    Bewusst schmal: Zeilen als Wörterbücher. Damit lässt sich der Rest ohne
    Sage testen.
    """

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[Row]: ...


@dataclass
class OdbcDatabase:
    connection: Any

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        cursor = self.connection.cursor()
        try:
            if params:
                cursor.execute(sql, *params)
            else:
                cursor.execute(sql)
            columns = [column[0] for column in cursor.description or ()]
            return [dict(zip(columns, values, strict=True)) for values in cursor.fetchall()]
        except Exception as error:  # pragma: no cover - hängt am Treiber
            raise SageUnavailable(f"Abfrage gescheitert: {error}") from error
        finally:
            cursor.close()

    def tables(self, pattern: str | None = None) -> list[Row]:
        cursor = self.connection.cursor()
        try:
            found = [
                {
                    "schema": row.table_schem,
                    "table": row.table_name,
                    "type": row.table_type,
                }
                for row in cursor.tables()
            ]
        finally:
            cursor.close()
        if pattern is None:
            return found
        needle = pattern.lower()
        return [row for row in found if needle in str(row["table"]).lower()]

    def columns(self, table: str) -> list[Row]:
        cursor = self.connection.cursor()
        try:
            return [
                {
                    "column": row.column_name,
                    "type": row.type_name,
                    "size": row.column_size,
                    "nullable": bool(row.nullable),
                }
                for row in cursor.columns(table=table)
            ]
        finally:
            cursor.close()


@contextmanager
def connect(sage: SageConnection, *, timeout: int = 30) -> Iterator[OdbcDatabase]:
    try:
        import pyodbc
    except ImportError as error:
        raise SageUnavailable(
            "pyodbc ist nicht installiert. pip install -r requirements.txt"
        ) from error

    try:
        connection = pyodbc.connect(sage.connection_string(), timeout=timeout)
    except Exception as error:
        raise SageUnavailable(
            f"Keine Verbindung zur Sage ({sage.redacted()}): {error}"
        ) from error

    # Lesender Zugriff: nichts zu committen, und ein versehentliches Schreiben
    # soll nicht dauerhaft werden.
    connection.autocommit = False
    try:
        yield OdbcDatabase(connection)
    finally:
        connection.rollback()
        connection.close()


class StaticDatabase:
    """Datenquelle aus vorgegebenen Zeilen. Für Tests und Trockenläufe."""

    def __init__(self, answers: dict[str, list[Row]]) -> None:
        self._answers = answers
        self.asked: list[str] = []

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        self.asked.append(sql)
        for key, rows in self._answers.items():
            if key in sql:
                return rows
        raise SageUnavailable(f"Keine Antwort hinterlegt für: {sql[:60]}...")
