"""Reading an object in a year: types, roles, names, confessions."""

from __future__ import annotations

from gov_gazetteer_mcp import model
from gov_gazetteer_mcp.soap import decode
from gov_gazetteer_mcp.typetable import TYPES

from .test_soap import body


def obj(name: str) -> dict:
    return decode("getObject", body(name))


def test_the_type_table_is_gov_s_whole_list():
    assert len(TYPES) == 276
    assert TYPES[103] == ("Standesamt", "civil office")
    assert TYPES[29] == ("Kirchspiel", "ecclesiastical")


def test_roles_follow_gov_s_groups():
    assert model.role_of_type(55) == "settlement"  # Dorf
    assert model.role_of_type(36) == "civil"  # Landkreis
    assert model.role_of_type(29) == "parish"  # Kirchspiel
    assert model.role_of_type(27) == "church_district"  # Kirchenkreis
    assert model.role_of_type(103) == "registry"
    assert model.role_of_type(3) == "court"  # Amtsgericht
    assert model.role_of_type(71) == "confederation"
    assert model.role_of_type(9999) == "other"


def test_a_type_gov_adds_later_is_learnt():
    try:
        model.learn_type(9999, ["Neuer Typ", "Siedlung"])
        assert model.type_name(9999) == "Neuer Typ" and model.role_of_type(9999) == "settlement"
    finally:
        model.LEARNT_TYPES.pop(9999, None)


def test_types_and_names_in_a_year():
    kreis = obj("getObject__adm-145332.xml")
    assert model.best_type(kreis, 1900) == 36
    assert model.name_at(kreis, 1900) == "Aschersleben"
    assert model.name_at(kreis, 1902) == "Quedlinburg"
    assert model.name_at(kreis, None) == "Quedlinburg"


def test_an_object_whose_types_all_exclude_a_year_did_not_exist_then():
    kanton = obj("getObject__object-275612.xml")  # 1807 to 1813
    assert model.existed(kanton, 1810) and not model.existed(kanton, 1850)


def test_dated_names_follow_the_year():
    stolp = obj("getObject__STOOLPJO84ML.xml")  # Stolp to 1945, Słupsk from 1945
    assert model.name_at(stolp, 1900, "deu") == "Stolp"
    assert model.name_at(stolp, 1900, "pol") == "Stolp"  # no Polish name held then
    assert model.name_at(stolp, 1950, "deu") == "Słupsk"


def test_among_names_that_hold_the_language_asked_for_wins():
    parish = obj("getObject__object-1141435.xml")  # undated in German and in Polish
    assert model.name_at(parish, 1900, "deu") == "Stolp (St. Otto)"
    assert model.name_at(parish, 1900, "pol") == "Słupsk"
    found = model.names_at(parish, 1887, "deu")
    assert [n["name"] for n in found][:2] == ["Stolp (S. Otto)", "Stolp (Hl. Otto)"]


def test_confessions_are_read_and_labelled():
    parish = obj("getObject__object-154674.xml")
    assert model.denominations_at(parish, 1900) == ["ev"]
    assert model.denomination_label("ev").startswith("evangelisch")
    assert model.denomination_label("zz") == "zz"


def test_confession_words_cover_the_protestant_family():
    assert model.CONFESSIONS["protestant"] == {"ev", "lu", "lt", "rf"}
    assert "ev" in model.CONFESSIONS["lutheran"]  # a united parish kept Lutherans' books
    assert model.CONFESSIONS["catholic"] == {"rk"}


def test_names_are_compared_without_case_or_accents():
    assert model.fold("Lübeck") == model.fold("lubeck")
    assert model.fold("Lange  Straße") == "lange strasse"
