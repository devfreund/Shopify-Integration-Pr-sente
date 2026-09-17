"""Die Kette Zeilen -> Dokumente -> Dateien über die Kommandozeile.

Deckt ab, was sonst ein Handlauf zeigen würde. Sage kommt nicht vor: die Zeilen
kommen aus ``--rows``.
"""

import json
from pathlib import Path

from sage_export.cli import main

DOMAIN = "praesentetesting.myshopify.com"
SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "rows.example.json"

CONFIG = """
[sage]
dsn = "WKF_SAGE"
mandant = 1

[export]
root = "export"

[shops]
WKF = "{domain}"
"""


def setup(tmp_path) -> list[str]:
    config = tmp_path / "sage-export.toml"
    config.write_text(CONFIG.format(domain=DOMAIN), encoding="utf-8")
    return [
        "--config",
        str(config),
        "export",
        "--rows",
        str(SAMPLE),
    ]


def shop_dir(tmp_path) -> Path:
    return tmp_path / "export" / DOMAIN


def test_check_meldet_die_offenen_sage_felder(tmp_path, capsys):
    config = tmp_path / "sage-export.toml"
    config.write_text(CONFIG.format(domain=DOMAIN), encoding="utf-8")

    code = main(["--config", str(config), "check"])

    assert code == 1
    assert "queries.py" in capsys.readouterr().out


def test_trockenlauf_schreibt_nichts(tmp_path, capsys):
    code = main([*setup(tmp_path), "--dry-run"])

    assert code == 0
    assert not shop_dir(tmp_path).exists()
    assert "Trockenlauf" in capsys.readouterr().out


def test_export_legt_das_shop_verzeichnis_an(tmp_path):
    assert main(setup(tmp_path)) == 0

    assert sorted(path.name for path in shop_dir(tmp_path).iterdir()) == [
        "children",
        "deactivations.json",
        "sets",
    ]
    assert len(list((shop_dir(tmp_path) / "children").glob("*.json"))) == 5


def test_set_entspricht_der_fixture(tmp_path):
    main(setup(tmp_path))

    written = json.loads(
        (shop_dir(tmp_path) / "sets" / "824006.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "fixtures"
            / DOMAIN
            / "sets"
            / "824006.json"
        ).read_text(encoding="utf-8")
    )

    assert written == fixture


def test_kinder_entsprechen_der_fixture(tmp_path):
    main(setup(tmp_path))

    fixtures = Path(__file__).resolve().parents[3] / "fixtures" / DOMAIN / "children"
    for path in (shop_dir(tmp_path) / "children").glob("*.json"):
        expected = json.loads((fixtures / path.name).read_text(encoding="utf-8"))
        assert json.loads(path.read_text(encoding="utf-8")) == expected


def test_zweiter_lauf_schreibt_nicht_neu(tmp_path, capsys):
    main(setup(tmp_path))
    capsys.readouterr()

    main(setup(tmp_path))

    assert "0 geschrieben" in capsys.readouterr().out


def test_unbekannter_shop_wird_gemeldet(tmp_path, capsys):
    code = main([*setup(tmp_path), "--shop", "anderer.myshopify.com"])

    assert code == 1
    assert "anderer.myshopify.com" in capsys.readouterr().err


def test_leere_zeilendatei_loescht_nichts(tmp_path, capsys):
    main(setup(tmp_path))
    leer = tmp_path / "leer.json"
    leer.write_text('{"children": [], "sets": [], "bom": []}', encoding="utf-8")
    config = tmp_path / "sage-export.toml"

    code = main(
        ["--config", str(config), "export", "--rows", str(leer)]
    )

    assert code == 1
    assert "nichts gelöscht" in capsys.readouterr().err
    assert (shop_dir(tmp_path) / "sets" / "824006.json").exists()


def test_fehlende_zeilendatei_wird_gemeldet(tmp_path, capsys):
    config = tmp_path / "sage-export.toml"
    config.write_text(CONFIG.format(domain=DOMAIN), encoding="utf-8")

    code = main(
        ["--config", str(config), "export", "--rows", str(tmp_path / "fehlt.json")]
    )

    assert code == 1
    assert "nicht gefunden" in capsys.readouterr().err
