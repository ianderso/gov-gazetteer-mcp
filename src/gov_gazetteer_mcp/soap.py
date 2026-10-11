"""SOAP envelopes for GOV's ComplexService, built by hand, and their answers parsed.

GOV's services are SOAP 1.1, RPC style with literal parts (observed in the
WSDL at https://gov.genealogy.net/services/ComplexService?wsdl, 2026-10-11).
A request is a ``ws:<operation>`` element in the body whose parts are
unqualified children; an integer list is a ``ws:int`` sequence and a string
list a ``ws:item`` one. The answer is ``ws:<operation>Response`` holding one
unqualified ``out`` element.

Only read operations are ever built (:data:`READ_OPERATIONS`). GOV's
ChangeService, which edits the gazetteer, has no envelope here at all.

The standard library's parser reads the answers. A document type declaration
is refused before parsing: SOAP forbids one, and refusing it closes the door
on entity expansion.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from xml.sax.saxutils import escape

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
WS = "http://gov.genealogy.net/ws"
DATA = "http://gov.genealogy.net/data"

#: The ComplexService operations this server may call, and nothing else. All
#: of them read; none changes anything.
READ_OPERATIONS = frozenset(
    {
        "getObject",
        "getObjectByExternalId",
        "getChildObjects",
        "searchByName",
        "searchByNameAndType",
        "searchDescendantsByName",
        "getTypeDescription",
    }
)

#: Object properties GOV records, each a list of dated values.
PROPERTIES = (
    "external-reference",
    "url",
    "name",
    "type",
    "population",
    "postal-code",
    "w-number",
    "denomination",
    "municipal-id",
    "area",
    "households",
    "buildings",
)

#: Relations from an object to another, each dated.
RELATIONS = ("part-of", "located-in", "represents")

#: A part's value: text, or a list of ints, or a list of strings.
Part = str | int | list[int] | list[str]


class SoapFault(Exception):
    """GOV answered with a SOAP fault.

    ``kind`` is the fault's detail element (``NoSuchObject``, ``UnknownType``,
    ``NoSuchReference``) or empty, and ``text`` its faultstring.
    """

    def __init__(self, kind: str, text: str, code: str = ""):
        """Record the fault."""
        self.kind = kind
        self.text = text
        self.code = code
        super().__init__(f"{kind or code}: {text}")


class NotSoap(Exception):
    """The answer is not a SOAP envelope this module can read."""


def envelope(operation: str, parts: list[tuple[str, Part]]) -> bytes:
    """The request body for one read operation.

    Raises
    ------
    ValueError
        If ``operation`` is not one of :data:`READ_OPERATIONS`.
    """
    if operation not in READ_OPERATIONS:
        raise ValueError(f"{operation!r} is not a read operation this server calls")
    inner = []
    for name, value in parts:
        if isinstance(value, list):
            if all(isinstance(v, int) for v in value):
                items = "".join(f"<ws:int>{int(v)}</ws:int>" for v in value)
            else:
                items = "".join(f"<ws:item>{escape(str(v))}</ws:item>" for v in value)
            inner.append(f"<{name}>{items}</{name}>")
        else:
            inner.append(f"<{name}>{escape(str(value))}</{name}>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="{SOAP_ENV}" xmlns:ws="{WS}">'
        f"<soapenv:Body><ws:{operation}>{''.join(inner)}</ws:{operation}>"
        "</soapenv:Body></soapenv:Envelope>"
    ).encode()


def _root(body: bytes) -> ET.Element:
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in body.lower():
        raise NotSoap("the answer carries a document type declaration")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise NotSoap(f"the answer is not well-formed XML ({exc})") from None


def fault_of(body: bytes) -> SoapFault | None:
    """The SOAP fault in an answer, or None if it holds none or is not SOAP."""
    try:
        return _fault_in(_root(body))
    except NotSoap:
        return None


def _fault_in(root: ET.Element) -> SoapFault | None:
    fault = root.find(f"{{{SOAP_ENV}}}Body/{{{SOAP_ENV}}}Fault")
    if fault is None:
        return None
    detail = fault.find("detail")
    kind = ""
    if detail is not None and len(detail):
        kind = detail[0].tag.rsplit("}", 1)[-1]
    return SoapFault(
        kind,
        (fault.findtext("faultstring") or "").strip(),
        (fault.findtext("faultcode") or "").strip(),
    )


def decode(operation: str, body: bytes) -> Any:
    """Parse an answer into plain data, cacheable as JSON.

    Returns a parsed object (dict) for getObject and getObjectByExternalId,
    a list of them for the searches and getChildObjects, and a list of
    strings for getTypeDescription.

    Raises
    ------
    SoapFault
        If the answer is a fault.
    NotSoap
        If it is not a SOAP envelope, or not the answer to ``operation``.
    """
    root = _root(body)
    if root.tag != f"{{{SOAP_ENV}}}Envelope":
        raise NotSoap("the answer is XML but not a SOAP envelope")
    soap_body = root.find(f"{{{SOAP_ENV}}}Body")
    if soap_body is None:
        raise NotSoap("the SOAP envelope has no body")
    if (fault := _fault_in(root)) is not None:
        raise fault
    response = soap_body.find(f"{{{WS}}}{operation}Response")
    if response is None:
        raise NotSoap(f"the answer is not a {operation} response")
    out = response.find("out")
    if operation in ("getObject", "getObjectByExternalId"):
        if out is None or not out.get("id"):
            raise NotSoap("the answer holds no object")
        return parse_object(out)
    if operation == "getTypeDescription":
        return [] if out is None else [(i.text or "").strip() for i in out.findall(f"{{{WS}}}item")]
    if out is None:
        return []
    return [parse_object(o) for o in out.findall(f"{{{DATA}}}object")]


def _span(el: ET.Element) -> dict[str, Any]:
    """An element's dates, in the raw form :class:`gov_gazetteer_mcp.dates.Span` reads."""
    raw: dict[str, Any] = {}
    for attr, key in (("begin-year", "begin_year"), ("end-year", "end_year"), ("year", "year")):
        if (value := el.get(attr)) is not None and value.lstrip("-").isdigit():
            raw[key] = int(value)
    timespan = el.find(f"{{{DATA}}}timespan")
    if timespan is not None:
        for end in ("begin", "end"):
            point = timespan.find(f"{{{DATA}}}{end}")
            if point is not None and (jd := point.get("jd", "")).lstrip("-").isdigit():
                precision = point.get("precision", "2")
                raw[end] = [int(jd), int(precision) if precision.isdigit() else 2]
    return raw


def _sources(el: ET.Element) -> list[str]:
    return [s.get("ref", "") for s in el.findall(f"{{{DATA}}}source") if s.get("ref")]


def parse_object(el: ET.Element) -> dict[str, Any]:
    """One GOV object as plain data.

    ``props`` maps each property name to a list of ``{value, lang?, span,
    sources?}``; ``rels`` maps each relation to a list of ``{ref, span,
    sources?}``; ``notes`` is a list of ``{lang?, text}``.
    """
    obj: dict[str, Any] = {"id": el.get("id", "")}
    if deprecated := el.get("deprecated"):
        obj["deprecated"] = deprecated
    if modified := el.get("last-modification"):
        obj["modified"] = modified
    pos = el.find(f"{{{DATA}}}position")
    if pos is not None:
        try:
            position: dict[str, Any] = {
                "lat": float(pos.get("lat", "")),
                "lon": float(pos.get("lon", "")),
            }
        except ValueError:
            position = {}
        if position:
            if (height := pos.get("height", "")).lstrip("-").isdigit():
                position["height"] = int(height)
            if kind := pos.get("type"):
                position["kind"] = kind
            obj["position"] = position
    props: dict[str, list[dict[str, Any]]] = {}
    for name in PROPERTIES:
        for item in el.findall(f"{{{DATA}}}{name}"):
            value = item.get("value")
            if value is None:
                continue
            entry: dict[str, Any] = {"value": value.strip()}
            if lang := item.get("lang"):
                entry["lang"] = lang
            if span := _span(item):
                entry["span"] = span
            if sources := _sources(item):
                entry["sources"] = sources
            props.setdefault(name, []).append(entry)
    obj["props"] = props
    rels: dict[str, list[dict[str, Any]]] = {}
    for name in RELATIONS:
        for item in el.findall(f"{{{DATA}}}{name}"):
            if not (ref := item.get("ref")):
                continue
            entry = {"ref": ref}
            if span := _span(item):
                entry["span"] = span
            if sources := _sources(item):
                entry["sources"] = sources
            rels.setdefault(name, []).append(entry)
    obj["rels"] = rels
    notes = []
    for note in el.findall(f"{{{DATA}}}note"):
        text = " ".join((note.findtext(f"{{{DATA}}}text") or "").split())
        if text:
            entry = {"text": text}
            if lang := note.get("lang"):
                entry["lang"] = lang
            notes.append(entry)
    if notes:
        obj["notes"] = notes
    return obj
