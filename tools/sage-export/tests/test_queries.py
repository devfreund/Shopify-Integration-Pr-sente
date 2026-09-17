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


incomplete = pytest.mark.skipif(
    not queries.open_placeholders(),
    reason="Die Sage-Abfragen sind vollständig — diese Sperre greift nicht mehr.",
)


@incomplete
def test_unvollstaendige_abfragen_verhindern_den_export():
    # Solange Sage-Felder fehlen, darf nichts gegen die Produktivdaten laufen.
    database = StaticDatabase({"SELECT": []})

    with pytest.raises(queries.QueriesNotConfigured) as error:
        fetch_rows(database, mandant=1)

    assert "queries.py" in str(error.value)
    assert database.asked == []


@incomplete
def test_ensure_ready_nennt_jede_offene_stelle():
    with pytest.raises(queries.QueriesNotConfigured) as error:
        queries.ensure_ready()

    message = str(error.value)
    for names in queries.open_placeholders().values():
        for name in names:
            assert name in message
