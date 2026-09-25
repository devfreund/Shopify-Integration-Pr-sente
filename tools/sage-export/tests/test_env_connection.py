"""Verbindungsdaten aus der Umgebung — das Gegenstück zu Vinseccos Connect."""

import pytest

from sage_export import queries
from sage_export.config import (
    DEFAULT_EXTRA,
    ENV_NAMES,
    ConfigError,
    SageConnection,
    default_driver,
)
from sage_export.env import SKIP_VAR, first_env, load_env_files

#: conftest.py leert die Verbindungsvariablen und sperrt das Lesen von .env.
assert ENV_NAMES["server"][0] == "WKF_SERVER"


def test_wkf_namen_werden_gelesen(monkeypatch):
    monkeypatch.setenv("WKF_SERVER", "sql.intern.wkf")
    monkeypatch.setenv("WKF_DATABASE", "OL_WKF")
    monkeypatch.setenv("WKF_UID", "sage_readonly")
    monkeypatch.setenv("WKF_PWD", "geheim")

    sage = SageConnection.from_env()

    assert sage.server == "sql.intern.wkf"
    assert sage.database == "OL_WKF"
    assert sage.user == "sage_readonly"
    assert "PWD=geheim" in sage.connection_string()
    assert "geheim" not in sage.redacted()


def test_db_namen_sind_der_fallback(monkeypatch):
    monkeypatch.setenv("DB_SERVER", "sql.intern.wkf")
    monkeypatch.setenv("DB_NAME", "OL_WKF")
    monkeypatch.setenv("DB_USER", "sage_readonly")
    monkeypatch.setenv("DB_PASSWORD", "geheim")

    sage = SageConnection.from_env()

    assert sage.server == "sql.intern.wkf"
    assert sage.database == "OL_WKF"
    assert sage.user == "sage_readonly"


def test_wkf_hat_vorrang_vor_db(monkeypatch):
    monkeypatch.setenv("WKF_SERVER", "richtig.intern.wkf")
    monkeypatch.setenv("DB_SERVER", "falsch.intern.wkf")
    monkeypatch.setenv("WKF_DATABASE", "OL_WKF")
    monkeypatch.setenv("WKF_UID", "sage_readonly")
    monkeypatch.setenv("WKF_PWD", "geheim")

    assert SageConnection.from_env().server == "richtig.intern.wkf"


def test_fehlende_variablen_werden_benannt(monkeypatch):
    monkeypatch.setenv("WKF_SERVER", "sql.intern.wkf")

    with pytest.raises(ConfigError) as error:
        SageConnection.from_env()

    assert "WKF_DATABASE" in str(error.value)


def test_benutzer_ohne_passwort_bricht_ab(monkeypatch):
    monkeypatch.setenv("WKF_SERVER", "sql.intern.wkf")
    monkeypatch.setenv("WKF_DATABASE", "OL_WKF")
    monkeypatch.setenv("WKF_UID", "sage_readonly")

    with pytest.raises(ConfigError, match="WKF_PWD"):
        SageConnection.from_env()


def test_windows_anmeldung_braucht_kein_passwort(monkeypatch):
    monkeypatch.setenv("WKF_SERVER", "sql.intern.wkf")
    monkeypatch.setenv("WKF_DATABASE", "OL_WKF")
    monkeypatch.setenv("WKF_TRUSTED_CONNECTION", "1")

    sage = SageConnection.from_env()

    assert sage.trusted_connection is True
    assert "Trusted_Connection=yes" in sage.connection_string()
    assert "PWD=" not in sage.connection_string()


def test_treiber_standard_und_zertifikat(monkeypatch):
    monkeypatch.setenv("WKF_SERVER", "sql.intern.wkf")
    monkeypatch.setenv("WKF_DATABASE", "OL_WKF")
    monkeypatch.setenv("WKF_TRUSTED_CONNECTION", "1")

    sage = SageConnection.from_env()

    assert sage.driver == default_driver()
    assert DEFAULT_EXTRA["TrustServerCertificate"] == "yes"
    assert "TrustServerCertificate=yes" in sage.connection_string()


def test_kein_host_und_kein_passwort_im_code():
    # Ohne Umgebung darf nichts vorbelegt sein, sonst landet der Exporter
    # unbemerkt auf einer falschen Datenbank.
    with pytest.raises(ConfigError):
        SageConnection.from_env()


def test_dotenv_datei_wird_gelesen_und_ueberschreibt_nichts(monkeypatch, tmp_path):
    monkeypatch.delenv(SKIP_VAR, raising=False)
    (tmp_path / ".env").write_text(
        '# Kommentar\nWKF_SERVER="aus.datei"\nWKF_DATABASE=OL_WKF\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("WKF_DATABASE", "aus.der.shell")

    load_env_files(tmp_path)

    assert first_env("WKF_SERVER") == "aus.datei"
    assert first_env("WKF_DATABASE") == "aus.der.shell"


def test_stuecklistenspalten_sind_belegt():
    # Parent, Kind und Menge stehen in der Architektur-Blaupause und sind keine
    # Platzhalter mehr.
    assert queries.BOM_PARENT_COLUMN.endswith(".Stueckliste")
    assert queries.BOM_CHILD_COLUMN.endswith(".Element")
    assert queries.BOM_QTY_COLUMN.endswith(".Menge")

    offen = queries.open_placeholders().get("bom", [])
    assert "BOM_CHILD_COLUMN" not in offen
    assert "BOM_QTY_COLUMN" not in offen
    assert "KHKArtikelStueckliste" in queries.BOM_SQL
    assert "KHKArtikelStueckliste" in queries.SETS_COMPLETE_SQL


def test_connect_wkf_ist_das_gegenstueck_zu_vinsecco():
    from sage_export.odbc import connect_wkf

    assert "Get_PYODBC_Connection_WKF" in (connect_wkf.__doc__ or "")
