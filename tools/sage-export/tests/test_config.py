import pytest

from sage_export.config import ConfigError, load_config

MINIMAL = """
[sage]
dsn = "WKF_SAGE"
mandant = 1

[shops]
WKF = "praesentetesting.myshopify.com"
"""


def write(tmp_path, text):
    path = tmp_path / "sage-export.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_liest_die_minimalkonfiguration(tmp_path):
    config = load_config(write(tmp_path, MINIMAL))

    assert config.sage.dsn == "WKF_SAGE"
    assert config.mandant == 1
    assert config.shops == {"WKF": "praesentetesting.myshopify.com"}
    assert config.export_root == (tmp_path / "export").resolve()
    assert config.explode_bom is False


def test_passwort_in_der_datei_wird_abgelehnt(tmp_path):
    text = MINIMAL.replace('dsn = "WKF_SAGE"', 'dsn = "WKF_SAGE"\npassword = "geheim"')

    with pytest.raises(ConfigError, match="SAGE_EXPORT_PASSWORD"):
        load_config(write(tmp_path, text))


def test_passwort_kommt_aus_der_umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGE_EXPORT_USER", "sage_readonly")
    monkeypatch.setenv("SAGE_EXPORT_PASSWORD", "geheim")

    config = load_config(write(tmp_path, MINIMAL))

    assert "PWD=geheim" in config.sage.connection_string()
    assert "geheim" not in config.sage.redacted()


def test_benutzer_ohne_passwort_bricht_ab(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGE_EXPORT_USER", "sage_readonly")
    monkeypatch.delenv("SAGE_EXPORT_PASSWORD", raising=False)

    with pytest.raises(ConfigError, match="SAGE_EXPORT_PASSWORD"):
        load_config(write(tmp_path, MINIMAL))


def test_ohne_dsn_und_ohne_treiber_bricht_ab(tmp_path):
    text = """
[sage]
mandant = 1

[shops]
WKF = "praesentetesting.myshopify.com"
"""

    with pytest.raises(ConfigError, match="dsn"):
        load_config(write(tmp_path, text))


def test_fehlender_mandant_bricht_ab(tmp_path):
    with pytest.raises(ConfigError, match="mandant"):
        load_config(write(tmp_path, MINIMAL.replace("mandant = 1", "")))


def test_shops_muessen_myshopify_domains_sein(tmp_path):
    text = MINIMAL.replace(
        'WKF = "praesentetesting.myshopify.com"', 'WKF = "praesente.de"'
    )

    with pytest.raises(ConfigError, match="myshopify"):
        load_config(write(tmp_path, text))


def test_fehlende_shopzuordnung_bricht_ab(tmp_path):
    text = MINIMAL.split("[shops]")[0]

    with pytest.raises(ConfigError, match=r"\[shops\]"):
        load_config(write(tmp_path, text))


def test_unbekanntes_kennzeichen_wird_nicht_geraten(tmp_path):
    config = load_config(write(tmp_path, MINIMAL))

    with pytest.raises(ConfigError, match="ANDERS"):
        config.domain_for("ANDERS")
