import pytest

from sage_export.config import Config, ConfigError, SageConnection
from sage_export.model import ChildDocument, Component, SetDocument, ShopExport
from sage_export.pipeline import build_exports, deactivations_for, SourceRows
from sage_export.writer import write_export

DOMAIN = "praesentetesting.myshopify.com"


def config(tmp_path, explode_bom=False, shops=None, article_groups=("800",), evaluation_groups=(0,)):
    return Config(
        sage=SageConnection(dsn="WKF_SAGE"),
        mandant=1,
        export_root=tmp_path,
        shops=shops if shops is not None else {"WKF": DOMAIN},
        article_groups=article_groups,
        evaluation_groups=evaluation_groups,
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
                "article_group": "800",
                "evaluation_group": 0,
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


def test_jahrgang_null_faellt_weg_artikelstamm_bleibt(tmp_path):
    from decimal import Decimal

    source = rows()
    source.children[0].update(
        {
            "jahrgang": "2025",
            "enthalt_sulfite": -1,
            "flascheninhalt": Decimal("0.75"),
            "in_verkehr_bringer": "Weinkontor Freund GmbH",
            "herkunftsland": "Südafrika",
            "region": "Coastal Region",
            "verkehrsbezeichnung": None,
        }
    )
    source.children[1].update(
        {"jahrgang": "0", "enthalt_sulfite": 0, "herkunftsland": "Südafrika"}
    )
    children = {
        child.sku: child
        for child in build_exports(source, config(tmp_path)).exports[0].children
    }
    wine = children["605091"].facts
    food = children["734103"].facts
    assert wine["jahrgang"] == "2025"
    assert wine["enthalt_sulfite"] is True
    assert wine["flascheninhalt"] == 0.75
    assert wine["herkunftsland"] == "Südafrika"
    assert "verkehrsbezeichnung" not in wine
    assert "jahrgang" not in food
    assert food["enthalt_sulfite"] is False
    assert children["734103"].html is None


def test_uebernimmt_html_unveraendert(tmp_path):
    report = build_exports(rows(), config(tmp_path))
    document = report.exports[0].sets[0]

    assert document.html == "<p>Südafrika für Genießer.</p>"
    assert document.kennzeichnung_html == "1.0 x False Bay …"


def test_sage_aktiv_minus_eins_ist_wahr(tmp_path):
    source = rows()
    source.sets[0]["active"] = -1
    source.children[0]["active"] = 0

    report = build_exports(source, config(tmp_path))

    assert report.exports[0].sets[0].active is True
    assert report.exports[0].children[0].active is False


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


def test_shop_key_ordnet_nicht_mehr_zu(tmp_path):
    report = build_exports(rows(), config(tmp_path, shops={"ANDERS": DOMAIN}))

    assert [export.domain for export in report.exports] == [DOMAIN]


def test_fehlendes_shop_key_nimmt_den_einzigen_shop(tmp_path):
    source = rows()
    for row in source.sets:
        row["shop_key"] = None

    report = build_exports(source, config(tmp_path))

    assert [export.domain for export in report.exports] == [DOMAIN]


def test_zwei_shops_bekommen_denselben_gefilterten_satz(tmp_path):
    source = rows()
    source.sets.append(
        {
            "parent_sku": "8990070",
            "title": "SP Amazon Weinpaket Italien",
            "active": 1,
            "article_group": "800",
            "evaluation_group": 80000,
        }
    )
    source.bom.append(
        {"parent_sku": "8990070", "sku": "999001", "qty": 1, "position": 10}
    )
    source.children.append(
        {
            "sku": "999001",
            "title": "Nur im Weinpaket",
            "active": 1,
        }
    )
    shops = {"WKF": DOMAIN, "ANDERS": "anderer.myshopify.com"}

    report = build_exports(source, config(tmp_path, shops=shops))

    assert [export.domain for export in report.exports] == [
        "anderer.myshopify.com",
        DOMAIN,
    ]
    for export in report.exports:
        assert [document.parent_sku for document in export.sets] == ["824006"]
        assert "8990070" not in {document.parent_sku for document in export.sets}
        assert "999001" not in {child.sku for child in export.children}
    assert [document.parent_sku for document in report.exports[0].sets] == [
        document.parent_sku for document in report.exports[1].sets
    ]


def test_fehlende_article_groups_schreiben_nichts(tmp_path):
    with pytest.raises(ConfigError, match="article_groups"):
        build_exports(rows(), config(tmp_path, article_groups=(), evaluation_groups=()))


def test_sets_complete_zeilen_werden_gruppiert():
    from sage_export.pipeline import source_rows_from_complete

    source = source_rows_from_complete(
        [
            {
                "shop_key": "WKF",
                "parent_sku": "824006",
                "title": "Präsent African Spice-Box",
                "active": 1,
                "html": "<p>unverändert</p>",
                "kennzeichnung_html": "1.0 x Wein …",
                "sku": "605091",
                "child_title": "False Bay Slow Chenin Blanc",
                "child_active": 1,
                "product_type": "Wein",
                "child_html": None,
                "qty": 1,
                "position": 10,
                "nutrition_html": None,
            },
            {
                "shop_key": "WKF",
                "parent_sku": "824006",
                "title": "Präsent African Spice-Box",
                "active": 1,
                "html": "<p>unverändert</p>",
                "kennzeichnung_html": "1.0 x Wein …",
                "sku": "734103",
                "child_title": "Chutney",
                "child_active": 1,
                "product_type": "Food",
                "child_html": None,
                "qty": 2,
                "position": 20,
                "nutrition_html": "<p>Zutaten unverändert</p>",
            },
        ]
    )

    assert [row["parent_sku"] for row in source.sets] == ["824006"]
    assert [row["sku"] for row in source.children] == ["605091", "734103"]
    assert [(row["sku"], row["qty"]) for row in source.bom] == [
        ("605091", 1),
        ("734103", 2),
    ]
    assert source.sets[0]["html"] == "<p>unverändert</p>"
    assert source.children[0]["title"] == "False Bay Slow Chenin Blanc"
    assert source.bom[1]["nutrition_html"] == "<p>Zutaten unverändert</p>"


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
