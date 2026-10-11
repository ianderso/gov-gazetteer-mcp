"""Reading a parsed GOV object: its types, names and confession in a given year.

The objects come from :func:`gov_gazetteer_mcp.soap.parse_object`. Nothing
here makes a request.
"""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

from .dates import ATTESTED_ELSEWHERE, OUTSIDE, RANK, UNDATED, Span
from .typetable import TYPES

#: GOV's "Staatenbund": the German Confederation, the League of Nations, the
#: EU, the UN. GOV records memberships in them as enclosures; they are not a
#: level of government, and a civil chain leaves them out.
CONFEDERATION = 71

#: Types that keep registers for a congregation: Kirchspiel, Pfarrei,
#: Kirchengemeinde, Pfarrkuratie, Pfarr-Rektorat, Dompfarrei, Expositur,
#: Sprengel, Filiale (whose books are often kept by the mother parish), and
#: Jüdische Gemeinde.
PARISH_TYPES = frozenset({12, 13, 29, 41, 42, 43, 49, 92, 219, 282})

#: Buildings that stand in a place and "represent" a parish: Kirche, Kloster,
#: Abtei, Nebenkirche, Kapelle.
CHURCH_BUILDING_TYPES = frozenset({26, 30, 124, 244, 245})

#: The Standesamt, and GOV's retired type for its building.
REGISTRY_TYPES = frozenset({103, 104})

#: The Jewish congregation type, which carries no confession code.
JEWISH_CONGREGATION = 282

#: Roles a civil chain follows.
CHAIN_ROLES = frozenset({"civil", "settlement"})

#: What each of GOV's confession codes means, observed on GOV's own item
#: pages on 2026-10-11. Another code is passed through as it is.
DENOMINATIONS = {
    "ev": "evangelisch (Protestant)",
    "lu": "lutherisch (Lutheran)",
    "lt": "evangelisch-lutherisch (Lutheran)",
    "rf": "reformiert (Reformed)",
    "rk": "römisch-katholisch (Roman Catholic)",
    "ak": "altkatholisch (Old Catholic)",
}

_PROTESTANT = frozenset({"ev", "lu", "lt", "rf"})

#: What a ``confession`` argument may say, and the codes it keeps. Lutheran
#: and Reformed keep "ev" too: a united (uniert) Prussian parish kept the
#: registers of both.
CONFESSIONS: dict[str, frozenset[str]] = {
    "protestant": _PROTESTANT,
    "evangelical": _PROTESTANT,
    "evangelisch": _PROTESTANT,
    "ev": _PROTESTANT,
    "lutheran": frozenset({"lu", "lt", "ev"}),
    "lutherisch": frozenset({"lu", "lt", "ev"}),
    "lu": frozenset({"lu", "lt", "ev"}),
    "lt": frozenset({"lu", "lt", "ev"}),
    "reformed": frozenset({"rf", "ev"}),
    "reformiert": frozenset({"rf", "ev"}),
    "rf": frozenset({"rf", "ev"}),
    "catholic": frozenset({"rk"}),
    "roman catholic": frozenset({"rk"}),
    "katholisch": frozenset({"rk"}),
    "römisch-katholisch": frozenset({"rk"}),
    "rk": frozenset({"rk"}),
    "old catholic": frozenset({"ak"}),
    "altkatholisch": frozenset({"ak"}),
    "ak": frozenset({"ak"}),
    "jewish": frozenset(),
    "jüdisch": frozenset(),
}


def this_year() -> int:
    """The current year, for "now"."""
    return date.today().year


def fold(text: str) -> str:
    """Text without case or accents, for comparing names: Lübeck == lubeck."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.replace("ß", "ss").casefold().split())


#: Types GOV added after the table was copied, learnt this session from
#: ``getTypeDescription``: type id -> (German name, group).
LEARNT_TYPES: dict[int, tuple[str, str]] = {}

#: The group names ``getTypeDescription`` answers with, in English.
LIVE_GROUPS = {
    "Siedlung": "settlement",
    "Wohnplatz": "settlement",
    "Verwaltung": "civil",
    "(politische) Verwaltung": "civil",
    "Kirche": "ecclesiastical",
    "Gericht": "judicial",
    "Zivilverwaltung": "civil office",
}


def known_type(type_id: int) -> bool:
    """Whether this table, or this session, knows the type."""
    return type_id in TYPES or type_id in LEARNT_TYPES


def learn_type(type_id: int, description: list[str]) -> None:
    """Keep a type ``getTypeDescription`` described: ``[name, group]`` in German."""
    name = description[0] if description and description[0] else f"type {type_id}"
    group = LIVE_GROUPS.get(description[1] if len(description) > 1 else "", "unknown")
    LEARNT_TYPES[type_id] = (name, group)


def _type(type_id: int) -> tuple[str, str]:
    return TYPES.get(type_id) or LEARNT_TYPES.get(type_id) or (f"type {type_id}", "unknown")


def type_name(type_id: int) -> str:
    """GOV's German name of a type, or ``type <id>`` for one not known."""
    return _type(type_id)[0]


def type_group(type_id: int) -> str:
    """GOV's group of a type, in English; ``unknown`` for a type not known."""
    return _type(type_id)[1]


def role_of_type(type_id: int) -> str:
    """What a type means for this server's questions.

    ``registry``, ``parish``, ``church_building``, ``confederation``,
    ``civil``, ``settlement``, ``church_district`` (any other
    ecclesiastical type), ``court``, or ``other``.
    """
    if type_id in REGISTRY_TYPES:
        return "registry"
    if type_id in PARISH_TYPES:
        return "parish"
    if type_id in CHURCH_BUILDING_TYPES:
        return "church_building"
    if type_id == CONFEDERATION:
        return "confederation"
    group = type_group(type_id)
    return {
        "civil": "civil",
        "settlement": "settlement",
        "ecclesiastical": "church_district",
        "judicial": "court",
    }.get(group, "other")


def entries(obj: dict, prop: str) -> list[dict[str, Any]]:
    """An object's values of one property, each with its decoded ``span``."""
    out = []
    for raw in obj.get("props", {}).get(prop, []):
        out.append({**raw, "span": Span.from_raw(raw.get("span"))})
    return out


def relations(obj: dict, kind: str) -> list[dict[str, Any]]:
    """An object's relations of one kind, each with its decoded ``span``."""
    return [
        {**raw, "span": Span.from_raw(raw.get("span"))} for raw in obj.get("rels", {}).get(kind, [])
    ]


def type_ids(obj: dict) -> list[int]:
    """Every type id an object has had, in GOV's order, without repeats."""
    out: list[int] = []
    for t in entries(obj, "type"):
        if t["value"].isdigit() and int(t["value"]) not in out:
            out.append(int(t["value"]))
    return out


def types_at(obj: dict, year: int) -> list[tuple[int, str]]:
    """The object's types that may hold in ``year``, best evidence first.

    Each is ``(type id, validity)``; types whose dates exclude the year are
    left out.
    """
    found = []
    for t in entries(obj, "type"):
        if not t["value"].isdigit():
            continue
        validity = t["span"].validity(year)
        if validity != OUTSIDE:
            found.append((int(t["value"]), validity))
    found.sort(key=lambda tv: -RANK[tv[1]])
    return found


def existed(obj: dict, year: int) -> bool:
    """False only when GOV dates every type of the object and none covers the year."""
    types = entries(obj, "type")
    return not types or any(t["span"].validity(year) != OUTSIDE for t in types)


def best_type(obj: dict, year: int | None) -> int | None:
    """The type that best describes the object in ``year``; with no year, now.

    Falls back to the type that ended last when none holds in the year.
    """
    found = types_at(obj, this_year() if year is None else year)
    if found:
        return found[0][0]
    dated = [t for t in entries(obj, "type") if t["value"].isdigit()]
    if not dated:
        return None
    if year is not None:
        # The nearest type to the year asked about.
        return int(min(dated, key=lambda t: _distance(t["span"], year))["value"])
    return int(max(dated, key=lambda t: t["span"].sort_end())["value"])


def role_at(obj: dict, year: int | None) -> str:
    """The object's role in ``year`` (or now), from :func:`best_type`."""
    tid = best_type(obj, year)
    return "other" if tid is None else role_of_type(tid)


def names_at(obj: dict, year: int, language: str = "deu") -> list[dict[str, Any]]:
    """Names that may hold in ``year``: ``language`` first, then the best evidenced.

    Each is ``{name, lang, validity}``. A name whose dates exclude the year
    is left out. Language comes first because GOV dates names unevenly: a
    German name attested in one directory should not lose to an undated
    Polish one when German was asked for, nor the reverse.
    """
    found = []
    for order, n in enumerate(entries(obj, "name")):
        validity = n["span"].validity(year)
        if validity == OUTSIDE or not n["value"]:
            continue
        found.append((n.get("lang") == language, RANK[validity], -order, n, validity))
    found.sort(key=lambda f: (f[0], f[1], f[2]), reverse=True)
    out, seen = [], set()
    for _, _, _, n, validity in found:
        key = (n["value"], n.get("lang"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": n["value"], "lang": n.get("lang", ""), "validity": validity})
    return out


def name_at(obj: dict, year: int | None, language: str = "deu") -> str:
    """The object's best name in ``year``; its id if it has no name.

    With no year: its name in ``language`` that is current or ended last
    (an undated name counts as current), else any language's. For a year
    no name covers: the name in ``language`` nearest to it.
    """
    names = [n for n in entries(obj, "name") if n["value"]]
    if not names:
        return obj.get("id", "")
    preferred = [n for n in names if n.get("lang") == language] or names
    if year is None:
        return max(preferred, key=lambda n: n["span"].sort_end())["value"]
    found = names_at(obj, year, language)
    if found:
        return found[0]["name"]
    return min(preferred, key=lambda n: _distance(n["span"], year))["value"]


def _distance(span: Span, year: int) -> int:
    """Years between a span and ``year``; 0 when the span holds then."""
    if span.begin is not None and year < span.begin.year:
        return span.begin.year - year
    if span.end is not None and year > span.end.year:
        return year - span.end.year
    if span.attested is not None and span.begin is None and span.end is None:
        return abs(year - span.attested)
    return 0


def all_names(obj: dict) -> list[str]:
    """Every distinct name the object has carried."""
    return list(dict.fromkeys(n["value"] for n in entries(obj, "name") if n["value"]))


def denominations_at(obj: dict, year: int | None) -> list[str]:
    """Confession codes recorded for the object in ``year`` (all of them with no year).

    A code attested in another year counts: a congregation's confession
    seldom changes, and GOV often records it from one directory only.
    """
    out = []
    for d in entries(obj, "denomination"):
        if year is not None and d["span"].validity(year) == OUTSIDE:
            continue
        if d["value"] and d["value"] not in out:
            out.append(d["value"])
    return out


def denomination_label(code: str) -> str:
    """A confession code in words, or the code itself if GOV's meaning is unknown here."""
    return DENOMINATIONS.get(code, code)


def certainty(validity: str) -> str:
    """How sure GOV's dates make a link for the year asked about, in words."""
    return {
        "dated": "dated",
        "attested": "attested in that year",
        UNDATED: "undated",
        ATTESTED_ELSEWHERE: "attested in another year only",
    }.get(validity, validity)
