"""Hand-built SOAP envelopes, and GOV's answers parsed."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from gov_gazetteer_mcp.soap import (
    READ_OPERATIONS,
    NotSoap,
    SoapFault,
    decode,
    envelope,
    fault_of,
)

from .conftest import FIXTURES, NIKOLAUSBERG

WS = "{http://gov.genealogy.net/ws}"


def body(name: str) -> bytes:
    data = (FIXTURES / name).read_bytes()
    head, _, rest = data.partition(b"\n")
    return rest if head.isdigit() else data


def test_an_envelope_carries_unqualified_parts_and_escapes_text():
    root = ET.fromstring(envelope("searchByName", [("placename", "Ober & <Unter>")]))
    op = root[0][0]
    assert op.tag == WS + "searchByName"
    assert op.find("placename").text == "Ober & <Unter>"


def test_lists_become_ws_ints_or_items():
    root = ET.fromstring(envelope("searchByNameAndType", [("types", [51, 55])]))
    assert [i.text for i in root[0][0].find("types").findall(WS + "int")] == ["51", "55"]


def test_only_read_operations_are_built():
    for op in ("saveObject", "merge", "saveSource"):
        with pytest.raises(ValueError):
            envelope(op, [])
    assert "saveObject" not in READ_OPERATIONS


def test_an_object_is_parsed_with_its_dates():
    obj = decode("getObject", body("getObject__NIKERG-W3401.xml"))
    assert obj["id"] == NIKOLAUSBERG
    assert obj["position"] == {"lat": 51.5626, "lon": 9.9832, "kind": "p"}
    types = obj["props"]["type"]
    assert {"value": "39", "span": {"begin_year": 1885}} in types
    gemeinde = next(r for r in obj["rels"]["part-of"] if r["ref"] == "object_1349305")
    assert gemeinde["span"] == {"begin": [2383610, 0], "end": [2438580, 2]}
    assert obj["notes"] == [{"text": "1852: Nicolausberg, Dorf und Kloster-Vorwerk"}]


def test_a_search_answer_is_a_list_of_whole_objects():
    found = decode("searchByName", body("searchByName__Quedlinburg.xml"))
    assert len(found) == 24
    town = next(o for o in found if o["id"] == "object_289891")
    assert len(town["props"]["population"]) > 5  # the whole object, not a summary


def test_an_empty_search_is_an_empty_list():
    assert decode("searchByName", body("searchByName__Quedlinbrug.xml")) == []


def test_a_fault_is_raised_with_its_kind():
    with pytest.raises(SoapFault) as caught:
        decode("getObject", body("getObject__XXXXXXJO00AA.xml"))
    assert caught.value.kind == "NoSuchObject"
    assert "XXXXXXJO00AA" in caught.value.text
    assert fault_of(body("getObject__XXXXXXJO00AA.xml")).kind == "NoSuchObject"


def test_a_document_type_declaration_is_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
    with pytest.raises(NotSoap):
        decode("getObject", bomb)
    assert fault_of(bomb) is None


@pytest.mark.parametrize(
    "answer",
    [b"<html><body>Making sure you are not a bot</body></html>", b"not xml", b"<a/>"],
)
def test_anything_else_is_not_soap(answer):
    with pytest.raises(NotSoap):
        decode("getObject", answer)


def test_the_answer_must_be_to_the_operation_asked():
    with pytest.raises(NotSoap):
        decode("searchByName", body("getObject__NIKERG-W3401.xml"))
