"""Shared fixtures. Every test runs against a mocked GOV; nothing touches the network.

The fixtures under ``fixtures/`` are real ComplexService answers recorded on
2026-10-11 (see docs/API-NOTES.md), one file per request, named by the
operation and its arguments as :func:`fixture_name` spells them. A file whose
answer was not a 200 starts with the status on a line of its own. The places
are well known and neutral: Quedlinburg in the Harz, Lübeck, the village of
Nikolausberg near Göttingen, and Stolp (now Słupsk) in Pomerania, with the
Kreise, provinces and states above them.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from gov_gazetteer_mcp import server
from gov_gazetteer_mcp.client import ENDPOINT, GovHttp
from gov_gazetteer_mcp.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

#: Ids used across the suite.
NIKOLAUSBERG = "NIKERG_W3401"  # the village near Göttingen
QUEDLINBURG = "QUEURGJO51NT"  # the town in the Harz
LUEBECK = "LUBEC1JO53IU"  # the city
STOLP = "STOOLPJO84ML"  # the Pomeranian town, now Słupsk
KREIS_GOETTINGEN = "adm_133152"


def fixture_name(body: bytes) -> str:
    """The fixture file a SOAP request is answered from: ``<operation>__<arguments>.xml``."""
    root = ET.fromstring(body)
    operation = root[0][0]
    op = operation.tag.rsplit("}", 1)[-1]
    values = []
    for part in operation:
        values.append("-".join((c.text or "") for c in part) if len(part) else part.text or "")
    slug = "_".join(re.sub(r"[^A-Za-z0-9-]+", "-", v)[:40] for v in values)
    return f"{op}__{slug}.xml"


def recorded(name: str) -> httpx.Response:
    """A recorded answer as a response, with the status it was recorded with."""
    data = (FIXTURES / name).read_bytes()
    status = 200
    head, _, rest = data.partition(b"\n")
    if head.isdigit():
        status, data = int(head), rest
    return httpx.Response(status, content=data, headers={"content-type": "text/xml;charset=UTF-8"})


def answer_from_fixtures(request: httpx.Request) -> httpx.Response:
    """Answer a SOAP request from the recorded fixtures; 599 for anything unrecorded."""
    name = fixture_name(request.content)
    if not (FIXTURES / name).is_file():
        return httpx.Response(599, text=f"unrecorded request: {name}")
    return recorded(name)


def make_http(tmp_path: Path, **kwargs) -> GovHttp:
    """A client with no pacing and no back-off, caching under ``tmp_path``."""
    options = {"min_interval": 0.0, "backoff": 0.0}
    options.update(kwargs)
    return GovHttp(tmp_path / "cache", **options)


@pytest.fixture
def http(tmp_path) -> GovHttp:
    return make_http(tmp_path)


@pytest.fixture
def served(tmp_path, monkeypatch) -> GovHttp:
    """Install a fast test client as the server's client for the duration of a test."""
    c = make_http(tmp_path)
    monkeypatch.setattr(server.runtime, "http", c)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    return c


@pytest.fixture
def gov():
    """A respx router answering GOV from the fixtures. Any other request fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        route = router.post(ENDPOINT).mock(side_effect=answer_from_fixtures)
        yield route


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved."""
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


def operations(route: respx.Route) -> list[str]:
    """The fixture names of every request a route answered, in order."""
    return [fixture_name(call.request.content) for call in route.calls]


# --------------------------------------------------------------------------- #
# Argument building for whole-surface sweeps
# --------------------------------------------------------------------------- #
#: Errors a tool returns from its own input checks, before any work. A sweep
#: that gets one of these has not tested what it thinks it has.
LOCAL_VALIDATION_ERRORS = frozenset(
    {
        "invalid_id",
        "invalid_year",
        "invalid_name",
        "invalid_language",
        "no_criteria",
        "unknown_type",
        "unknown_confession",
    }
)

#: Arguments that carry each tool past its own checks.
VALID_ARGS: dict[str, dict[str, Any]] = {
    "gov_search": {"name": "Quedlinburg"},
    "gov_object": {"gov_id": QUEDLINBURG},
    "gov_place_at_date": {"gov_id": NIKOLAUSBERG, "year": 1900},
    "gov_registers": {"gov_id": NIKOLAUSBERG, "year": 1900},
    "gov_enclosures": {"gov_id": NIKOLAUSBERG},
    "cache_status": {},
}


def assert_reached_body(tool_name: str, result) -> None:
    """Fail if a sweep stopped at input validation instead of the tool's body."""
    if isinstance(result, dict) and result.get("error") in LOCAL_VALIDATION_ERRORS:
        raise AssertionError(
            f"{tool_name} rejected the sweep's arguments with {result['error']!r}; "
            f"update VALID_ARGS in tests/conftest.py. Message: {result.get('message')!r}"
        )
