import json

from sage_export.model import ChildDocument, Component, Deactivation, SetDocument, ShopExport
from sage_export.writer import write_export

DOMAIN = "praesentetesting.myshopify.com"


def example() -> ShopExport:
    return ShopExport(
        domain=DOMAIN,
        children=[
            ChildDocument(
                sku="605091",
                title="False Bay Slow Chenin Blanc",
                active=True,
                product_type="Wein",
            )
        ],
        sets=[
            SetDocument(
                parent_sku="824006",
                title="Präsent African Spice-Box",
                active=True,
                components=[Component(sku="605091", qty=1.0)],
                html="<p>Südafrika für Genießer.</p>",
            )
        ],
    )


def test_schreibt_das_vereinbarte_layout(tmp_path):
    report = write_export(tmp_path, example())

    assert (tmp_path / DOMAIN / "children" / "605091.json").is_file()
    assert (tmp_path / DOMAIN / "sets" / "824006.json").is_file()
    assert (tmp_path / DOMAIN / "deactivations.json").is_file()
    assert len(report.written) == 3


def test_dokumente_entsprechen_dem_vertrag(tmp_path):
    write_export(tmp_path, example())

    document = json.loads(
        (tmp_path / DOMAIN / "sets" / "824006.json").read_text(encoding="utf-8")
    )

    assert document == {
        "parent_sku": "824006",
        "title": "Präsent African Spice-Box",
        "active": True,
        "html": "<p>Südafrika für Genießer.</p>",
        "components": [{"sku": "605091", "qty": 1}],
    }


def test_laesst_unveraenderte_dateien_liegen(tmp_path):
    write_export(tmp_path, example())
    target = tmp_path / DOMAIN / "sets" / "824006.json"
    before = target.stat().st_mtime_ns

    report = write_export(tmp_path, example())

    assert report.written == []
    assert len(report.unchanged) == 3
    assert target.stat().st_mtime_ns == before


def test_entfernt_was_sage_nicht_mehr_liefert(tmp_path):
    write_export(tmp_path, example())
    verschwunden = tmp_path / DOMAIN / "sets" / "824999.json"
    verschwunden.write_text("{}", encoding="utf-8")

    report = write_export(tmp_path, example())

    assert report.removed == ["sets/824999.json"]
    assert not verschwunden.exists()


def test_keep_stale_laesst_alles_stehen(tmp_path):
    write_export(tmp_path, example())
    verschwunden = tmp_path / DOMAIN / "sets" / "824999.json"
    verschwunden.write_text("{}", encoding="utf-8")

    report = write_export(tmp_path, example(), prune=False)

    assert report.removed == []
    assert verschwunden.exists()


def test_trockenlauf_faesst_nichts_an(tmp_path):
    report = write_export(tmp_path, example(), dry_run=True)

    assert len(report.written) == 3
    assert not (tmp_path / DOMAIN).exists()


def test_deaktivierungen_stehen_als_liste(tmp_path):
    export = example()
    export.deactivations = [Deactivation(sku="824100", role="parent")]

    write_export(tmp_path, export)

    assert json.loads(
        (tmp_path / DOMAIN / "deactivations.json").read_text(encoding="utf-8")
    ) == [{"sku": "824100", "role": "parent"}]


def test_hinterlaesst_keine_temporaeren_dateien(tmp_path):
    write_export(tmp_path, example())

    assert list((tmp_path / DOMAIN).rglob("*.tmp")) == []
