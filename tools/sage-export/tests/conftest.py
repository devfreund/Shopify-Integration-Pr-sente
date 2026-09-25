"""Tests laufen ohne Sage, ohne ODBC-Treiber und ohne echte Zugangsdaten.

Ohne diese Absicherung würde eine ``.env`` oder eine gesetzte ``WKF_*``-Variable
auf dem Entwicklerrechner in die Tests lecken — und ein Lauf wäre grün oder rot
je nachdem, wer ihn startet.
"""

import pytest

from sage_export.config import ENV_NAMES
from sage_export.env import SKIP_VAR

CONNECTION_VARS = tuple(
    dict.fromkeys(
        [name for names in ENV_NAMES.values() for name in names]
        + ["WKF_TRUSTED_CONNECTION"]
    )
)


@pytest.fixture(autouse=True)
def hermetische_umgebung(monkeypatch):
    monkeypatch.setenv(SKIP_VAR, "1")
    for name in CONNECTION_VARS:
        monkeypatch.delenv(name, raising=False)
