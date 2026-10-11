"""Ask GOV itself what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

Every call goes through the server's own client, one request at a time and at
least a second apart, with a fresh cache so nothing is answered from disk. The
checks cover:

* the WSDL still offers the read operations the server calls;
* name search still behaves as the descriptions say: word beginnings match,
  accents are ignored, a misspelling finds nothing;
* the chains, registers and enclosures the server was built against still come
  back: Nikolausberg near Göttingen in 1900, Quedlinburg under Napoleon in
  1810, Stolp's Standesamt in 1900 and its Polish chain in 1950, and the
  city of Posen on either side of 1919-20;
* external ids and unknown ids are still answered as recorded.

It is not a test module: pytest does not collect it, and CI never runs it,
because the suite must never depend on a volunteer-run service being up. About
a hundred requests; allow two or three minutes.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx

from gov_gazetteer_mcp import server
from gov_gazetteer_mcp.client import ENDPOINT, GovHttp, user_agent
from gov_gazetteer_mcp.config import load_config
from gov_gazetteer_mcp.soap import READ_OPERATIONS


def top(result: dict) -> str:
    return result["chain"][-1]["name"]


def chain_has(result: dict, name: str, type_: str) -> bool:
    return any(level["name"] == name and level["type"] == type_ for level in result["chain"])


#: (tool, arguments, check, what the check means).
CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "gov_search",
        {"name": "Quedlinburg"},
        lambda r: r["candidates"][0]["gov_id"] == "QUEURGJO51NT",
        "searchByName: the town comes first among Quedlinburg's 24 objects",
    ),
    (
        "gov_search",
        {"name": "Quedlin", "place_type": "Stadt (Siedlung)"},
        lambda r: [c["gov_id"] for c in r["candidates"]] == ["QUEURGJO51NT"],
        "a word beginning matches (Quedlin finds Quedlinburg)",
    ),
    (
        "gov_search",
        {"name": "Lubeck", "place_type": "Stadt (Siedlung)"},
        lambda r: any("Lübeck" in c["name"] for c in r["candidates"]),
        "accents are ignored (Lubeck finds Lübeck)",
    ),
    (
        "gov_search",
        {"name": "Quedlinbrug"},
        lambda r: r["total"] == 0,
        "a misspelling finds nothing: no fuzzy matching",
    ),
    (
        "gov_search",
        {"name": "Nikolausberg", "within": "adm_133152"},
        lambda r: r["candidates"][0]["gov_id"] == "NIKERG_W3401",
        "searchDescendantsByName inside Kreis Göttingen",
    ),
    (
        "gov_object",
        {"gov_id": "geonames:2851465"},
        lambda r: r["gov_id"] == "QUEURGJO51NT",
        "getObjectByExternalId: a GeoNames id names Quedlinburg",
    ),
    (
        "gov_object",
        {"gov_id": "XXXXXXJO00AA"},
        lambda r: r["error"] == "not_found",
        "an unknown id is a NoSuchObject fault, reported as not_found",
    ),
    (
        "gov_place_at_date",
        {"gov_id": "NIKERG_W3401", "year": 1900},
        lambda r: (
            chain_has(r, "Göttingen", "Landkreis")
            and chain_has(r, "Hannover", "Provinz")
            and top(r) == "Deutsches Reich"
        ),
        "Nikolausberg 1900: Landkreis Göttingen, Provinz Hannover, the German Empire",
    ),
    (
        "gov_place_at_date",
        {"gov_id": "QUEURGJO51NT", "year": 1810},
        lambda r: chain_has(r, "Quedlinburg", "Kanton") and top(r) == "Westfalen",
        "Quedlinburg 1810: a canton of the Kingdom of Westphalia",
    ),
    (
        "gov_registers",
        {"gov_id": "STOOLPJO84ML", "year": 1900},
        lambda r: (
            [s["gov_id"] for s in r.get("standesamt", [])] == ["object_1150193"]
            and {p["confession"][0]["code"] for p in r["parishes"]} >= {"ev", "rk"}
        ),
        "Stolp 1900: GOV links the Standesamt and both parishes directly",
    ),
    (
        "gov_registers",
        {"gov_id": "NIKERG_W3401", "year": 1900},
        lambda r: (
            r["parishes_of_churches_in_the_place"][0]["gov_id"] == "object_154674"
            and r["standesamt_candidates"][0]["gov_id"] == "object_1152183"
        ),
        "Nikolausberg 1900: the parish through its building, the Standesamt by name",
    ),
    (
        "gov_place_at_date",
        {"gov_id": "STOOLPJO84ML", "year": 1950, "language": "pol"},
        lambda r: r["name"] == "Słupsk" and top(r) != "Deutsches Reich",
        "Stolp 1950: Słupsk, in Poland",
    ),
    (
        "gov_enclosures",
        {"gov_id": "NIKERG_W3401", "to_year": 1945},
        lambda r: (
            r["places"][0]["enclosed_by"][0]["gov_id"] == "object_1349305"
            and any(p["gov_id"] == "adm_133152" for p in r["places"])
        ),
        "Nikolausberg's dated enclosures to 1945, the Gemeinde first",
    ),
]


async def wsdl() -> bool:
    """The WSDL still lists every operation the server calls."""
    async with httpx.AsyncClient(headers={"User-Agent": user_agent()}, timeout=30) as client:
        text = (await client.get(ENDPOINT + "?wsdl")).text
    offered = set(re.findall(r'operation name="([A-Za-z]+)"', text))
    missing = READ_OPERATIONS - offered
    ok = not missing
    print(f"{'PASS' if ok else 'FAIL'}  WSDL offers every read operation the server calls")
    if missing:
        print(f"      missing: {sorted(missing)}")
    return ok


async def posen() -> int:
    """The city of Posen: German in 1910, not in 1925."""
    failed = 0
    found = json.loads(
        (
            await server.mcp.call_tool(
                "gov_search", {"name": "Posen", "place_type": "Stadt (Siedlung)"}
            )
        )
        .content[0]
        .text
    )
    city = next(
        (c for c in found.get("candidates", []) if "Poznań" in c.get("other_names", [])), None
    )
    if city is None:
        print("FAIL  Posen: no town named Posen with the Polish name Poznań")
        return 1
    for year, german in ((1910, True), (1925, False)):
        args = {"gov_id": city["gov_id"], "year": year}
        result = json.loads((await server.mcp.call_tool("gov_place_at_date", args)).content[0].text)
        ok = "error" not in result and (top(result) == "Deutsches Reich") is german
        failed += not ok
        where = "in the German Empire" if german else "no longer in the German Empire"
        print(f"{'PASS' if ok else 'FAIL'}  Posen {year}: {where}")
        if not ok:
            print(f"      got: {json.dumps(result, ensure_ascii=False)[:400]}")
    return failed


async def main() -> int:
    cfg = load_config()
    failed = 0 if await wsdl() else 1
    with tempfile.TemporaryDirectory() as cache:
        http = GovHttp(
            Path(cache), timeout=cfg.timeout, min_interval=cfg.min_interval, contact=cfg.contact
        )
        server.runtime.config = cfg
        server.runtime.http = http
        for tool, args, check, meaning in CHECKS:
            result = json.loads((await server.mcp.call_tool(tool, args)).content[0].text)
            try:
                ok = ("error" not in result or "not_found" in meaning) and bool(check(result))
            except (KeyError, IndexError, TypeError):
                ok = False
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {tool}: {meaning}")
            if not ok:
                print(f"      got: {json.dumps(result, ensure_ascii=False)[:400]}")
        failed += await posen()
        print(f"\nrequests to GOV: {http.live_calls}")
        await http.aclose()
    total = len(CHECKS) + 3
    print(f"{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
