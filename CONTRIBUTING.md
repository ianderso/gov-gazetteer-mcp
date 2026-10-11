# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/gov-gazetteer-mcp
cd gov-gazetteer-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded GOV answers. It must never touch GOV: the service is run by
volunteers, and CI should not depend on it being up.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/gov_gazetteer_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. |
| `src/gov_gazetteer_mcp/walk.py` | Walking enclosures: the chain in a year, the parishes above a place, the dated hierarchy. |
| `src/gov_gazetteer_mcp/model.py` | Reading one parsed object in a year: types, roles, names, confessions. |
| `src/gov_gazetteer_mcp/dates.py` | GOV's dates (Julian Day Numbers with a precision, year attributes) and whether they hold in a year. |
| `src/gov_gazetteer_mcp/soap.py` | Hand-built SOAP envelopes for the read operations, and the parser for GOV's answers. |
| `src/gov_gazetteer_mcp/client.py` | The cached, paced HTTP client, the endpoint rule, the public-address check made at connect time, and the size cap. |
| `src/gov_gazetteer_mcp/typetable.py` | GOV's 276 object types, copied from its own type list. |
| `src/gov_gazetteer_mcp/shape.py` | Turning objects into results: type glosses, positions, the citation core, Gramps types. |
| `src/gov_gazetteer_mcp/config.py` | Settings from the environment and `.env`. |
| `docs/API-NOTES.md` | What GOV's web service was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is, and what is out of scope by decision. |
| `tests/fixtures/` | Recorded answers, one file per request, and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/test_security.py` | Every refusal against a steered model or a hostile answer. |
| `tests/live_check.py` | The one script that talks to GOV, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own. They
are dedented at import, so the budget measures the same text on every Python.

**The evidence distinction, kept.** A gazetteer entry is a finding aid. A
parish or Standesamt link is a lead to a register, never the record; results
that give one say so, and a contract test keeps the instructions saying it.

**The credit and the address on every object.** Any result that names a GOV
object carries its id and the address of its page, and every result credits
GOV and CompGen.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope. A sweep test calls every tool with GOV
failing and fails if one raises.

**Gentleness.** Nothing that calls GOV faster than once a second, nothing
that sends requests side by side, and nothing that reads more than a walk
needs. A walk is bounded (`DEFAULT_BUDGET` in `walk.py`); raise it only with
a reason.

**Nothing that writes to GOV, and nothing that works around a bot check.**
See [docs/DESIGN.md](docs/DESIGN.md#out-of-scope-by-decision).

**A new fixture recorded, not invented,** when a change depends on how GOV
answers, with what was observed and when added to `docs/API-NOTES.md`. Name
the file as `tests/conftest.py`'s `fixture_name` spells the request. Keep
fixtures to neutral, well-known places: never anyone's family research.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## Updating the type table

GOV publishes every object type at <https://gov.genealogy.net/type/list>. When
it adds types, copy the new rows into `typetable.py` (id, German name, and the
English group as the module's docstring maps it) and add a gloss in
`shape.GLOSS` if the type is common. Until then the server describes a new
type live, once per session.

## Releasing

A maintainer bumps `__version__` in `src/gov_gazetteer_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
