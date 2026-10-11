"""The tools, end to end, against GOV's recorded answers."""

from __future__ import annotations

import httpx
import respx

from gov_gazetteer_mcp.client import ENDPOINT

from .conftest import (
    KREIS_GOETTINGEN,
    LUEBECK,
    NIKOLAUSBERG,
    QUEDLINBURG,
    STOLP,
    answer_from_fixtures,
    call_tool,
    operations,
)

ITEM = "https://gov.genealogy.net/item/show/"


def names(chain: list[dict]) -> list[tuple[str, str]]:
    return [(level["name"], level["type"]) for level in chain]


# --------------------------------------------------------------------------- #
# gov_search
# --------------------------------------------------------------------------- #
async def test_search_puts_the_settlement_first_and_names_its_parents(served, gov):
    out = await call_tool("gov_search", name="Quedlinburg")
    assert out["total"] == 24 and out["returned"] == 20
    top = out["candidates"][0]
    assert top["gov_id"] == QUEDLINBURG and top["matches_whole_name"] is True
    assert (
        top["types"][0]["type"] == "Stadt (Siedlung)" and top["types"][0]["group"] == "settlement"
    )
    assert top["position"]["lat"] == 51.79009 and top["position"]["kind"] == "recorded position"
    assert top["parents"][0]["gov_id"] == "object_289891"
    assert top["parents"][0]["name"] == "Quedlinburg"
    assert top["url"] == ITEM + QUEDLINBURG
    assert out["credit"].startswith("GOV — Geschichtliches Orts-Verzeichnis")


async def test_search_ranks_whole_name_matches_before_partial_ones(served, gov):
    out = await call_tool("gov_search", name="Quedlinburg", limit=100)
    flags = [c["matches_whole_name"] for c in out["candidates"]]
    assert flags == sorted(flags, reverse=True)
    partial = [c["name"] for c in out["candidates"] if not c["matches_whole_name"]]
    assert "Quedlinburg-Land" in partial and "Quedlinburg/Dom" in partial


async def test_search_by_type_asks_gov_to_filter(served, gov):
    out = await call_tool("gov_search", name="Quedlinburg", place_type="Stadt (Siedlung)")
    assert [c["gov_id"] for c in out["candidates"]] == [QUEDLINBURG]
    assert operations(gov)[0] == "searchByNameAndType__Quedlinburg_51.xml"


async def test_search_within_a_kreis_uses_descendants(served, gov):
    out = await call_tool("gov_search", name="Nikolausberg", within=KREIS_GOETTINGEN)
    assert out["within"] == KREIS_GOETTINGEN
    ids = [c["gov_id"] for c in out["candidates"]]
    assert ids[0] == NIKOLAUSBERG and "object_1152183" in ids  # the Standesamt
    assert operations(gov)[0] == "searchDescendantsByName__adm-133152_Nikolausberg.xml"


async def test_search_within_filters_types_locally(served, gov):
    out = await call_tool(
        "gov_search", name="Nikolausberg", within=KREIS_GOETTINGEN, place_type="standesamt"
    )
    assert [c["gov_id"] for c in out["candidates"]] == ["object_1152183"]


async def test_a_zero_says_which_spellings_it_covers(served, gov):
    out = await call_tool("gov_search", name="Quedlinbrug")
    assert out["total"] == 0 and out["candidates"] == []
    assert "other spellings" in out["note"]


async def test_search_refuses_an_unknown_type_naming_the_choices(served, gov):
    out = await call_tool("gov_search", name="Quedlinburg", place_type="castle-ish")
    assert out["error"] == "unknown_type" and "Kirchspiel" in out["message"]
    assert gov.call_count == 0


async def test_search_needs_a_name(served, gov):
    assert (await call_tool("gov_search", name="   "))["error"] == "no_criteria"


async def test_search_reports_gov_s_cap(served):
    objects = "".join(
        f'<ns2:object id="X{i}"><ns2:name lang="deu" value="Ort {i}"/></ns2:object>'
        for i in range(500)
    )
    body = (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        '<ns1:searchByNameResponse xmlns:ns1="http://gov.genealogy.net/ws">'
        f'<out xmlns:ns2="http://gov.genealogy.net/data">{objects}</out>'
        "</ns1:searchByNameResponse></soap:Body></soap:Envelope>"
    )
    with respx.mock(assert_all_mocked=True) as router:
        router.post(ENDPOINT).mock(return_value=httpx.Response(200, text=body))
        out = await call_tool("gov_search", name="Ort", limit=3)
    assert out["total"] == 500 and out["returned"] == 3
    assert "500" in out["note"]


# --------------------------------------------------------------------------- #
# gov_object
# --------------------------------------------------------------------------- #
async def test_object_decodes_names_types_relations_and_dates(served, gov):
    out = await call_tool("gov_object", gov_id=NIKOLAUSBERG)
    assert out["name"] == "Nikolausberg"
    assert [(t["type"], t.get("from"), t.get("to")) for t in out["types"]] == [
        ("Ort", "1885", None),
        ("Dorf", None, "1885"),
    ]
    parents = {p["gov_id"]: p for p in out["part_of"]}
    assert parents["object_1349305"]["type"] == "Gemeinde"
    assert parents["object_1349305"]["periods"][0]["gramps_date"] == "from 1814 to 1964-07-03"
    assert out["part_of"][0]["gov_id"] == "object_320230"  # the current one first
    assert out["citation"]["url"] == ITEM + NIKOLAUSBERG
    assert out["citation"]["source"].endswith("(CompGen)")
    assert out["notes"] == [{"text": "1852: Nicolausberg, Dorf und Kloster-Vorwerk"}]


async def test_object_lists_what_lies_inside_it(served, gov):
    out = await call_tool("gov_object", gov_id="object_154674", children=True)
    assert out["types"][0]["type"] == "Kirchspiel"
    assert out["confessions"][0]["label"].startswith("evangelisch")
    assert out["children_total"] == 1
    assert out["children"][0]["type"] == "Kirche"
    assert out["children"][0]["periods"] == [{"relation": "represents", "undated": True}]


async def test_object_by_external_id(served, gov):
    out = await call_tool("gov_object", gov_id="geonames:2851465")
    assert out["gov_id"] == QUEDLINBURG
    assert {"value": "geonames:2851465"} in out["external_ids"]


async def test_object_by_gov_page_address(served, gov):
    out = await call_tool("gov_object", gov_id=ITEM + NIKOLAUSBERG)
    assert out["gov_id"] == NIKOLAUSBERG


async def test_an_unknown_object_is_not_found_not_an_outage(served, gov):
    out = await call_tool("gov_object", gov_id="XXXXXXJO00AA")
    assert out["error"] == "not_found" and "search for the place again" in out["message"]


async def test_object_refuses_a_malformed_id_without_asking(served, gov):
    for bad in ("a b c", "../etc", "http://example.org/x", ""):
        assert (await call_tool("gov_object", gov_id=bad))["error"] == "invalid_id", bad
    assert gov.call_count == 0


# --------------------------------------------------------------------------- #
# gov_place_at_date
# --------------------------------------------------------------------------- #
async def test_a_village_in_1900_climbs_to_the_empire(served, gov):
    out = await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1900)
    assert names(out["chain"]) == [
        ("Nikolausberg", "Ort"),
        ("Nikolausberg", "Gemeinde"),
        ("Göttingen", "Landkreis"),
        ("Hildesheim", "Regierungsbezirk"),
        ("Hannover", "Provinz"),
        ("Preußen", "Königreich"),
        ("Deutsches Reich", "Bundesstaat"),
    ]
    kreis = out["chain"][2]
    assert kreis["link"]["gramps_date"] == "from 1831 to 1964-07-03"
    assert kreis["link"]["certainty"] == "dated"
    assert kreis["url"] == ITEM + KREIS_GOETTINGEN
    assert out["chain_text"].startswith("Nikolausberg [Ort] > Nikolausberg [Gemeinde] >")
    assert out["requests_to_gov"] == 9


async def test_the_same_town_under_napoleon(served, gov):
    out = await call_tool("gov_place_at_date", gov_id=QUEDLINBURG, year=1810)
    assert names(out["chain"]) == [
        ("Quedlinburg", "Stadt (Siedlung)"),
        ("Quedlinburg", "Kanton"),
        ("Blankenburg", "Distrikt"),
        ("Saale", "Departement"),
        ("Westfalen", "Königreich"),
    ]
    assert any("memberships, not levels" in n for n in out["notes"])


async def test_a_town_that_became_an_urban_district(served, gov):
    before = await call_tool("gov_place_at_date", gov_id=QUEDLINBURG, year=1900)
    after = await call_tool("gov_place_at_date", gov_id=QUEDLINBURG, year=1925)
    assert ("Aschersleben", "Landkreis") in names(before["chain"])  # renamed in 1901
    assert ("Quedlinburg", "Stadtkreis") in names(after["chain"])
    assert ("Preußen", "Königreich") in names(before["chain"])
    assert ("Preußen", "Freistaat") in names(after["chain"])


async def test_a_free_city_in_the_empire(served, gov):
    out = await call_tool("gov_place_at_date", gov_id=LUEBECK, year=1900)
    assert names(out["chain"])[-2:] == [("Lübeck", "Land"), ("Deutsches Reich", "Bundesstaat")]
    assert any("'undated'" in n for n in out["notes"])


async def test_a_year_is_required_to_be_sensible(served, gov):
    out = await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=0)
    assert out["error"] == "invalid_year"
    out = await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1900, language="German")
    assert out["error"] == "invalid_language"
    assert gov.call_count == 0


async def test_a_second_year_reuses_the_cache(served, gov):
    await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1900)
    first = gov.call_count
    out = await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1901)
    assert gov.call_count == first and out["requests_to_gov"] == 0


async def test_a_parent_gov_cannot_serve_is_reported_not_raised(served):
    def failing_for_the_kreis(request: httpx.Request) -> httpx.Response:
        if b"adm_133152" in request.content:
            return httpx.Response(503, text="maintenance")
        return answer_from_fixtures(request)

    with respx.mock(assert_all_mocked=True) as router:
        router.post(ENDPOINT).mock(side_effect=failing_for_the_kreis)
        out = await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1900)
    assert names(out["chain"]) == [("Nikolausberg", "Ort"), ("Nikolausberg", "Gemeinde")]
    assert any("stopped answering" in n for n in out["notes"])


# --------------------------------------------------------------------------- #
# gov_registers
# --------------------------------------------------------------------------- #
async def test_registers_where_gov_links_parish_and_standesamt(served, gov):
    out = await call_tool("gov_registers", gov_id=STOLP, year=1900)
    assert [s["gov_id"] for s in out["standesamt"]] == ["object_1150193"]
    assert out["standesamt"][0]["link"]["gramps_date"] == "to 1945"
    confessions = {p["name"]: p["confession"][0]["code"] for p in out["parishes"]}
    assert confessions["Stolp"] == "ev" and confessions["Stolp (St. Otto)"] == "rk"
    ev = next(p for p in out["parishes"] if p["name"] == "Stolp")
    assert [a["type"] for a in ev["above"]] == ["Kirchenkreis", "Kirchenprovinz", "Landeskirche"]
    assert ev["link"]["certainty"] == "attested in another year only"
    assert out["courts"][0]["type"] == "Amtsgericht"
    assert "missing" not in out
    assert out["notes"][0].startswith("GOV is edited by volunteers")


async def test_registers_keep_one_confession(served, gov):
    out = await call_tool("gov_registers", gov_id=STOLP, year=1900, confession="catholic")
    assert {p["confession"][0]["code"] for p in out["parishes"]} == {"rk"}
    assert out["confession_filter"]["keeps"] == ["rk"]
    assert "Stolp" in out["confession_filter"]["left_out"]


async def test_registers_fall_back_to_the_church_in_the_place_and_say_so(served, gov):
    out = await call_tool("gov_registers", gov_id=NIKOLAUSBERG, year=1900)
    [lead] = out["parishes_of_churches_in_the_place"]
    assert lead["gov_id"] == "object_154674" and lead["type"] == "Kirchspiel"
    assert lead["church_building"]["type"] == "Kirche"
    assert any("usually, not always" in n for n in out["notes"])
    [candidate] = out["standesamt_candidates"]
    assert candidate["gov_id"] == "object_1152183"
    assert candidate["in"]["gov_id"] == KREIS_GOETTINGEN
    assert candidate["link"]["attested"] == 1883
    assert any("does not say it served this place" in n for n in out["notes"])


async def test_registers_say_plainly_when_a_level_is_missing(served, gov):
    out = await call_tool("gov_registers", gov_id=LUEBECK, year=1900)
    assert out["missing"] == ["GOV links no Standesamt to Lübeck or any place above it in 1900."]
    assert out["parishes"][0]["linked_via"] == {"gov_id": LUEBECK, "name": "the place itself"}


async def test_registers_before_civil_registration_say_so(served, gov):
    out = await call_tool("gov_registers", gov_id=STOLP, year=1870)
    assert any("1 October 1874 in Prussia" in n for n in out["notes"])


async def test_registers_refuse_an_unknown_confession(served, gov):
    out = await call_tool("gov_registers", gov_id=STOLP, year=1900, confession="pastafarian")
    assert out["error"] == "unknown_confession" and "lutheran" in out["message"]
    assert gov.call_count == 0


# --------------------------------------------------------------------------- #
# gov_enclosures
# --------------------------------------------------------------------------- #
async def test_enclosures_give_each_place_its_dated_parents(served, gov):
    out = await call_tool("gov_enclosures", gov_id=NIKOLAUSBERG, to_year=1945)
    places = {p["gov_id"]: p for p in out["places"]}
    village = out["places"][0]
    assert village["gov_id"] == NIKOLAUSBERG and village["gramps_type"] == "Locality"
    assert [e["gov_id"] for e in village["enclosed_by"]] == [
        "object_1349305",
        "object_275516",
        "object_1337387",
    ]
    assert village["enclosed_by"][0]["periods"][0]["gramps_date"] == "from 1814 to 1964-07-03"
    kreis = places[KREIS_GOETTINGEN]
    assert kreis["gramps_type"] == "County"
    assert kreis["enclosed_by"][0]["name"] == "Hildesheim"
    assert kreis["enclosed_by"][0]["type"] == "Regierungsbezirk"
    assert places["object_190315"]["gramps_type"] == "Country"
    assert out["window"] == {"from_year": None, "to_year": 1945}
    assert any("German Confederation" in n for n in out["notes"])
    assert "object_218127" not in places  # a confederation is no level


async def test_enclosures_refuse_a_reversed_window(served, gov):
    out = await call_tool("gov_enclosures", gov_id=NIKOLAUSBERG, from_year=1900, to_year=1800)
    assert out["error"] == "invalid_year"


# --------------------------------------------------------------------------- #
# cache_status
# --------------------------------------------------------------------------- #
async def test_cache_status_counts_requests_by_operation(served, gov):
    await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1900)
    out = await call_tool("cache_status")
    assert out["live_calls_this_session"] == 9
    assert out["calls_by_operation"] == {"getObject": 9}
    assert "a second apart" in out["note"]


# --------------------------------------------------------------------------- #
# Walk limits and boundary years, on made-up objects
# --------------------------------------------------------------------------- #
def soap_object(gov_id: str, inner: str) -> str:
    return (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        '<ns1:getObjectResponse xmlns:ns1="http://gov.genealogy.net/ws">'
        f'<out xmlns:ns2="http://gov.genealogy.net/data" id="{gov_id}">{inner}</out>'
        "</ns1:getObjectResponse></soap:Body></soap:Envelope>"
    )


#: A village that moved from one Kreis to another on 1 April 1937.
MOVED = {
    "dorf_1": '<ns2:name lang="deu" value="Dorf"/><ns2:type value="55"/>'
    '<ns2:part-of ref="kreis_a"><ns2:timespan><ns2:end jd="2428624" precision="2"/>'
    '</ns2:timespan></ns2:part-of><ns2:part-of ref="kreis_b"><ns2:timespan>'
    '<ns2:begin jd="2428625" precision="2"/></ns2:timespan></ns2:part-of>',
    "kreis_a": '<ns2:name lang="deu" value="Altkreis"/><ns2:type value="36"/>',
    "kreis_b": '<ns2:name lang="deu" value="Neukreis"/><ns2:type value="36"/>',
}


def made_up(request: httpx.Request) -> httpx.Response:
    for gov_id, inner in MOVED.items():
        if f"<itemId>{gov_id}</itemId>".encode() in request.content:
            return httpx.Response(200, text=soap_object(gov_id, inner))
    return httpx.Response(599)


async def test_a_place_that_moved_within_the_year_shows_both_and_says_so(served):
    with respx.mock(assert_all_mocked=True) as router:
        router.post(ENDPOINT).mock(side_effect=made_up)
        out = await call_tool("gov_place_at_date", gov_id="dorf_1", year=1937)
        later = await call_tool("gov_place_at_date", gov_id="dorf_1", year=1938)
    chained = {out["chain"][1]["name"], out["also_enclosed_by"][0]["name"]}
    assert chained == {"Altkreis", "Neukreis"}
    assert any("moved within 1937, from Altkreis to Neukreis" in n for n in out["notes"])
    assert [level["name"] for level in later["chain"]] == ["Dorf", "Neukreis"]
    assert "also_enclosed_by" not in later


async def test_a_walk_stops_at_its_request_limit_and_says_so(served, gov, monkeypatch):
    from gov_gazetteer_mcp import server, walk

    monkeypatch.setattr(server, "Walk", lambda http: walk.Walk(http, budget=2))
    out = await call_tool("gov_place_at_date", gov_id=NIKOLAUSBERG, year=1900)
    assert len(out["chain"]) == 2 and out["requests_to_gov"] == 2  # the place and its Gemeinde
    assert any("Stopped after 2 requests" in n for n in out["notes"])
