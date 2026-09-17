import pytest

from sage_export.config import Config, ConfigError, SageConnection
from sage_export.model import ChildDocument, Component, SetDocument, ShopExport
from sage_export.pipeline import build_exports, deactivations_for, SourceRows
from sage_export.writer import write_export

DOMAIN = "praesentetesting.myshopify.com"


def config(tmp_path, explode_bom=False, shops=None):
    return Config(
        sage=SageConnection(dsn="WKF_SAGE"),
        mandant=1,
        export_root=tmp_path,
        shops=shops if shops is not None else {"WKF": DOMAIN},
        explode_bom=explode_bom,
    )


def rows(**overrides) -> SourceRows:
    default = SourceRows(
        children=[
            {
                "shop_key": "WKF",
                "sku": "605091",
                "title": "False Bay Slow Chenin Blanc",
                "active": 1,
                "product_type": "Wein",
                "html": None,
            },
            {
                "shop_key": "WKF",
                "sku": "734103",
                "title": "Chutney",
                "active": 1,
                "product_type": "Food",
                "html": None,
            },
            {
                "shop_key": "WKF",
                "sku": "610001",
                "title": "Nicht im Set",
                "active": 1,
                "product_type": "Wein",
                "html": None,
            },
        ],
        sets=[
            {
                "shop_key": "WKF",
                "parent_sku": "824006",
                "title": "Präsent African Spice-Box",
                "active": 1,
                "html": "<p>Südafrika für Genießer.</p>",
                "kennzeichnung_html": "1.0 x False Bay …",
            }
        ],
        bom=[
            {"parent_sku": "824006", "sku": "605091", "qty": 1, "position": 10},
            {"parent_sku": "824006", "sku": "734103", "qty": 2, "position": 20},
        ],
    )
    for key, value in overrides.items():
        setattr(default, key, value)
    return default


def test_baut_ein_verzeichnis_je_shop(tmp_path):
    report = build_exports(rows(), config(tmp_path))

    assert [export.domain for export in report.exports] == [DOMAIN]


def test_uebernimmt_html_unveraendert(tmp_path):
    report = build_exports(rows(), config(tmp_path))
    document = report.exports[0].sets[0]

    assert document.html == "<p>Südafrika für Genießer.</p>"
    assert document.kennzeichnung_html == "1.0 x False Bay …"


def test_sage_kennzeichen_wird_wahrheitswert(tmp_path):
    report = build_exports(rows(), config(tmp_path))

    assert report.exports[0].sets[0].active is True


def test_unbekanntes_kennzeichen_bleibt_stehen(tmp_path):
    source = rows()
    source.sets[0]["active"] = "vielleicht"

    report = build_exports(source, config(tmp_path))

    # Node soll den echten Wert melden, statt hier geraten zu bekommen.
    assert report.exports[0].sets[0].active == "vielleicht"


def test_schreibt_nur_kinder_aus_der_stueckliste(tmp_path):
    report = build_exports(rows(), config(tmp_path))

    assert [child.sku for child in report.exports[0].children] == ["605091", "734103"]


def test_fehlendes_kind_wird_nicht_erfunden(tmp_path):
    source = rows()
    source.children = [source.children[0]]

    report = build_exports(source, config(tmp_path))

    assert [child.sku for child in report.exports[0].children] == ["605091"]
    assert any("734103" in warning for warning in report.warnings)


def test_set_ohne_stueckliste_wird_uebersprungen(tmp_path):
    report = build_exports(rows(bom=[]), config(tmp_path))

    assert report.exports == []
    assert any("824006" in warning for warning in report.warnings)


def test_unbekannter_shop_bricht_ab(tmp_path):
    with pytest.raises(ConfigError):
        build_exports(rows(), config(tmp_path, shops={"ANDERS": DOMAIN}))


def test_explosion_nur_wenn_konfiguriert(tmp_path):
    source = rows(
        bom=[
            {"parent_sku": "824006", "sku": "824100", "qty": 2, "position": 10},
            {"parent_sku": "824100", "sku": "605091", "qty": 3, "position": 10},
        ]
    )

    direct = build_exports(source, config(tmp_path))
    exploded = build_exports(source, config(tmp_path, explode_bom=True))

    assert [c.sku for c in direct.exports[0].sets[0].components] == ["824100"]
    assert [
        (c.sku, c.qty) for c in exploded.exports[0].sets[0].components
    ] == [("605091", 6)]


def full_export() -> ShopExport:
    return ShopExport(
        domain=DOMAIN,
        children=[ChildDocument(sku="605091", title="Wein", active=True)],
        sets=[
            SetDocument(
                parent_sku="824006",
                title="Set",
                active=True,
                components=[Component(sku="605091", qty=1)],
            )
        ],
    )


def test_erste_ausfuehrung_deaktiviert_nichts(tmp_path):
    assert deactivations_for(tmp_path / DOMAIN, full_export()) == []


def test_verschwundenes_set_wird_deaktiviert(tmp_path):
    write_export(tmp_path, full_export())
    leer = ShopExport(domain=DOMAIN)

    found = deactivations_for(tmp_path / DOMAIN, leer)

    assert [(entry.sku, entry.role) for entry in found] == [
        ("605091", "child"),
        ("824006", "parent"),
    ]


def test_deaktivierung_bleibt_bis_der_artikel_zurueckkehrt(tmp_path):
    write_export(tmp_path, full_export())
    leer = ShopExport(domain=DOMAIN)

    leer.deactivations = deactivations_for(tmp_path / DOMAIN, leer)
    write_export(tmp_path, leer)
    zweiter_lauf = deactivations_for(tmp_path / DOMAIN, ShopExport(domain=DOMAIN))

    assert [entry.sku for entry in zweiter_lauf] == ["605091", "824006"]


def test_rueckkehr_loescht_die_deaktivierung(tmp_path):
    write_export(tmp_path, full_export())
    leer = ShopExport(domain=DOMAIN)
    leer.deactivations = deactivations_for(tmp_path / DOMAIN, leer)
    write_export(tmp_path, leer)

    zurueck = full_export()

    assert deactivations_for(tmp_path / DOMAIN, zurueck) == []
