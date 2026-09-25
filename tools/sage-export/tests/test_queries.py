import pytest

from sage_export import queries
from sage_export.odbc import StaticDatabase
from sage_export.pipeline import fetch_rows


def test_offene_platzhalter_sind_dokumentiert():
    for names in queries.open_placeholders().values():
        for name in names:
            assert name in queries.OPEN_QUESTIONS, f"{name} ohne offene Frage"


def test_abfragen_liefern_die_erwarteten_aliase():
    for column in queries.SET_COLUMNS:
        assert f"AS {column}" in queries.SETS_SQL
    for column in queries.CHILD_COLUMNS:
        assert f"AS {column}" in queries.CHILDREN_SQL
    for column in queries.BOM_COLUMNS:
        assert f"AS {column}" in queries.BOM_SQL
    for column in queries.COMPLETE_COLUMNS:
        assert f"AS {column}" in queries.SETS_COMPLETE_SQL


def test_sets_complete_ist_die_vinsecco_analogie():
    sql = queries.SETS_COMPLETE_SQL
    assert "KHKArtikelStueckliste" in sql
    assert "stueckliste.Stueckliste" in sql
    assert "stueckliste.Element" in sql
    assert "stueckliste.Menge" in sql
    assert "parent.Bezeichnung1" in sql
    assert "child.Bezeichnung1" in sql
    assert "parent.LangtextHTML" not in sql
    assert sql.count("COALESCE(parent.DimensionstextHTML, CAST(parent.Dimensionstext AS nvarchar(max)))") == 2
    assert "child.USER_Land" in sql
    assert "child.USER_Sulfite" in sql
    assert "variante.USER_Land" not in sql
    assert "parent.DimensionstextHTML" in sql
    assert "CAST(parent.Dimensionstext AS nvarchar(max))" in sql
    assert "child.LangtextHTML" in sql
    assert "parent.Aktiv" in sql
    assert "child.Aktiv" in sql
    assert "stueckliste.Sortierung" in sql
    assert "ORDER BY stueckliste.Stueckliste, stueckliste.Sortierung, stueckliste.Element" in sql
    assert "parent.Stuecklistentyp = 1" in sql
    assert "parent.Artikelgruppe" in sql
    assert "parent.USER_Auswertungsgruppe" in sql
    assert "Artikelgruppe =" not in sql
    assert "CAST(NULL AS nvarchar(max))        AS nutrition_html" in sql
    assert "KHKPreislistenArtikel" in sql
    assert "USER_DefaultArtikel = -1" in sql
    assert "ListeID = 12" not in sql
    assert "ListeID = 39" not in sql
    assert "USER_JInhaltRTF" not in sql
    for forbidden in ("80100", "880", "800", "LangtextRTF", "USER_GastroEmpfehlung"):
        assert forbidden not in sql
    assert "80100" not in queries.SETS_SQL
    assert "artikel.LangtextHTML" in queries.SETS_SQL
    assert "artikel.DimensionstextHTML" in queries.SETS_SQL
    assert "stueckliste.Sortierung" in queries.BOM_SQL
    assert queries.open_placeholders() == {}


incomplete = pytest.mark.skipif(
    not queries.open_placeholders(),
    reason="Die Sage-Abfragen sind vollständig — diese Sperre greift nicht mehr.",
)


def test_fetch_rows_liest_sets_complete():
    database = StaticDatabase(
        {
            "KHKArtikelStueckliste": [
                {
                    "shop_key": None,
                    "parent_sku": "824006",
                    "title": "Präsent",
                    "active": 1,
                    "html": None,
                    "kennzeichnung_html": None,
                    "sku": "605091",
                    "child_title": "Wein",
                    "child_active": 1,
                    "product_type": None,
                    "child_html": None,
                    "qty": 1,
                    "position": None,
                    "nutrition_html": None,
                }
            ]
        }
    )

    source = fetch_rows(database, mandant=1)

    assert database.asked and "KHKArtikelStueckliste" in database.asked[0]
    assert [row["parent_sku"] for row in source.sets] == ["824006"]
    assert [row["sku"] for row in source.bom] == ["605091"]
    assert source.children[0]["title"] == "Wein"


@incomplete
def test_ensure_ready_nennt_jede_offene_stelle():
    with pytest.raises(queries.QueriesNotConfigured) as error:
        queries.ensure_ready()

    message = str(error.value)
    for names in queries.open_placeholders().values():
        for name in names:
            assert name in message
