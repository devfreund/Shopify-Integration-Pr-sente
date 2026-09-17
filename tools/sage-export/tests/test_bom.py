import pytest

from sage_export.bom import BomCycle, group_lines, resolve


def line(parent, sku, qty=1, position=None, nutrition_html=None):
    return {
        "parent_sku": parent,
        "sku": sku,
        "qty": qty,
        "position": position,
        "nutrition_html": nutrition_html,
    }


def test_haelt_die_sage_reihenfolge():
    grouped = group_lines(
        [
            line("824006", "735300", position=30),
            line("824006", "605091", position=10),
            line("824006", "734103", position=20),
        ]
    )

    assert [component.sku for component in grouped["824006"]] == [
        "605091",
        "734103",
        "735300",
    ]


def test_ohne_position_bleibt_die_lesereihenfolge():
    grouped = group_lines([line("824006", "605091"), line("824006", "734103")])

    assert [component.sku for component in grouped["824006"]] == ["605091", "734103"]


def test_fasst_doppelte_skus_nicht_zusammen():
    # Node lehnt das ab und nennt Datei und Feld. Hier zu addieren würde den
    # Datenfehler in Sage verdecken.
    grouped = group_lines([line("824006", "605091"), line("824006", "605091", qty=2)])

    assert [(c.sku, c.qty) for c in grouped["824006"]] == [("605091", 1), ("605091", 2)]


def test_menge_als_text_bleibt_text():
    grouped = group_lines([line("824006", "605091", qty="2")])

    assert grouped["824006"][0].qty == "2"


def test_leeres_nutrition_html_gilt_als_nicht_gesetzt():
    grouped = group_lines([line("824006", "605091", nutrition_html="   ")])

    assert grouped["824006"][0].nutrition_html is None


def test_direkte_zeilen_ohne_explosion():
    grouped = group_lines(
        [line("824006", "824100"), line("824100", "605091"), line("824100", "734103")]
    )

    assert [c.sku for c in resolve("824006", grouped)] == ["824100"]


def test_explosion_multipliziert_die_mengen():
    grouped = group_lines(
        [
            line("824006", "824100", qty=2),
            line("824100", "605091", qty=3),
            line("824100", "734103", qty=1),
        ]
    )

    exploded = resolve("824006", grouped, explode=True)

    assert [(c.sku, c.qty) for c in exploded] == [("605091", 6), ("734103", 2)]


def test_explosion_erkennt_kreise():
    grouped = group_lines([line("824006", "824100"), line("824100", "824006")])

    with pytest.raises(BomCycle):
        resolve("824006", grouped, explode=True)


def test_unbekannter_parent_hat_keine_komponenten():
    assert resolve("824999", group_lines([])) == []
