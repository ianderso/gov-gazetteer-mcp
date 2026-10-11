"""Turning parsed GOV objects into compact, citable tool results.

Every object a result names carries its GOV id and the address of its page
on GOV (``url``), and every result carries the credit GOV's makers ask for:
GOV and the Verein für Computergenealogie, with the object's address.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import model
from .dates import Span

#: The credit every result carries.
CREDIT = "GOV — Geschichtliches Orts-Verzeichnis, Verein für Computergenealogie (CompGen)"

#: An object's page on GOV, which is what gets cited.
ITEM_URL = "https://gov.genealogy.net/item/show/{}"

#: What GOV's position kinds mean, as its item pages label them (2026-10-11).
POSITION_KINDS = {
    "p": "recorded position",
    "c": "computed centre of the object (berechneter Mittelpunkt)",
    "e": "estimated (geschätzt)",
    "l": "position of the place the object stands in",
}

#: English for the types a genealogist meets most. GOV's German name is
#: always given too; it is the word the records and archive catalogues use.
GLOSS = {
    1: "district office area",
    2: "Prussian rural district (police and administration)",
    3: "local court",
    7: "federal state",
    13: "filial congregation",
    16: "free state",
    18: "municipality",
    23: "duchy",
    25: "canton",
    27: "deanery-level district of a Landeskirche",
    29: "parish",
    31: "kingdom",
    32: "district",
    34: "state",
    35: "regional Protestant body",
    36: "rural district",
    39: "place",
    40: "part of a place",
    42: "parish",
    43: "parish curacy",
    45: "province",
    46: "government region",
    50: "state",
    51: "town",
    53: "urban district",
    55: "village",
    60: "principality",
    61: "grand duchy",
    65: "village with a parish seat",
    66: "village with a place of worship",
    69: "hamlet",
    85: "rural municipality",
    92: "congregation",
    95: "independent town",
    103: "civil registry office",
    108: "manorial district",
    130: "federation (the country as a whole)",
    150: "town (municipality)",
    214: "empire",
    282: "Jewish congregation",
}

#: A suggested Gramps place type for each GOV type a dated hierarchy needs.
GRAMPS_TYPES: dict[int, str] = {
    **dict.fromkeys((50, 214, 130, 56, 72, 58, 160), "Country"),
    **dict.fromkeys((7, 34, 16, 31, 23, 61, 60, 33, 62, 128, 20), "State"),
    **dict.fromkeys((45, 86), "Province"),
    **dict.fromkeys((46, 73), "Region"),
    **dict.fromkeys((32, 36, 53, 95, 78, 99, 37, 110, 146, 270), "County"),
    **dict.fromkeys((1, 2, 5, 48, 94, 97, 108, 122, 127), "District"),
    **dict.fromkeys((18, 85, 140, 150, 163, 180, 218, 275, 14), "Municipality"),
    **dict.fromkeys((51, 93), "Town"),
    **dict.fromkeys((55, 65, 66), "Village"),
    **dict.fromkeys((69, 181, 229), "Hamlet"),
    **dict.fromkeys((21, 24, 64, 67), "Farm"),
    **dict.fromkeys((39, 40, 54, 120, 129, 158), "Locality"),
    **dict.fromkeys((8, 17, 87, 102, 111), "Building"),
    **dict.fromkeys((29, 42), "Parish"),
}


def url_of(gov_id: str) -> str:
    """The address of an object's page on GOV."""
    return ITEM_URL.format(gov_id)


def type_info(type_id: int | None) -> dict[str, Any]:
    """A type for a result: its id, GOV's German name, group and an English gloss."""
    if type_id is None:
        return {"type": None}
    out: dict[str, Any] = {
        "type": model.type_name(type_id),
        "type_id": type_id,
        "group": model.type_group(type_id),
    }
    if gloss := GLOSS.get(type_id):
        out["english"] = gloss
    return out


def brief(obj: dict, year: int | None = None, language: str = "deu") -> dict[str, Any]:
    """An object in one line: id, name and type in ``year`` (or now), and its page."""
    tid = model.best_type(obj, year)
    out: dict[str, Any] = {"gov_id": obj["id"], "name": model.name_at(obj, year, language)}
    out.update(type_info(tid))
    out["url"] = url_of(obj["id"])
    return out


def position(obj: dict) -> dict[str, Any] | None:
    """The object's coordinates, with what kind of position GOV says they are."""
    pos = obj.get("position")
    if not pos:
        return None
    out = {"lat": round(pos["lat"], 6), "lon": round(pos["lon"], 6)}
    if "height" in pos:
        out["height_m"] = pos["height"]
    if kind := pos.get("kind"):
        out["kind"] = POSITION_KINDS.get(kind, kind)
    return out


def dated_values(obj: dict, prop: str, *, first: int | None = None, last: int | None = None):
    """A property's values with their dates, optionally only those touching a window."""
    out = []
    for entry in model.entries(obj, prop):
        span: Span = entry["span"]
        if not span.overlaps(first, last):
            continue
        item: dict[str, Any] = {"value": entry["value"]}
        if entry.get("lang"):
            item["lang"] = entry["lang"]
        item.update(span.describe())
        if entry.get("sources"):
            item["sources"] = entry["sources"]
        out.append(item)
    return out


def names(obj: dict, *, first: int | None = None, last: int | None = None) -> list[dict]:
    """Every name with its language and dates (``gramps_date`` included)."""
    return [
        {"name": v.pop("value"), **v} for v in dated_values(obj, "name", first=first, last=last)
    ]


def types(obj: dict, *, first: int | None = None, last: int | None = None) -> list[dict]:
    """Every type with its dates, decoded."""
    out = []
    for v in dated_values(obj, "type", first=first, last=last):
        raw = v.pop("value")
        info = type_info(int(raw)) if raw.isdigit() else {"type": raw}
        out.append({**info, **v})
    return out


def gramps_type(obj: dict, year: int | None = None) -> str | None:
    """A suggested Gramps place type for the object in ``year`` (or now), or None."""
    tid = model.best_type(obj, year)
    return GRAMPS_TYPES.get(tid) if tid is not None else None


def retrieved(stored: float | None) -> str | None:
    """The day an answer was fetched from GOV, for "accessed" in a citation."""
    if not stored:
        return None
    return datetime.fromtimestamp(stored, UTC).date().isoformat()


def citation(obj: dict, stored: float | None, year: int | None = None) -> dict[str, Any]:
    """The citation core: the source, the entry's title and page, and when it was read."""
    tid = model.best_type(obj, year)
    title = model.name_at(obj, year)
    if tid is not None:
        title = f"{title} [{model.type_name(tid)}]"
    out: dict[str, Any] = {
        "source": CREDIT,
        "title": title,
        "gov_id": obj["id"],
        "url": url_of(obj["id"]),
    }
    if obj.get("modified"):
        out["entry_last_modified"] = obj["modified"][:10]
    if day := retrieved(stored):
        out["accessed"] = day
    return out
