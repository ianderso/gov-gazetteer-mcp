<!-- What this changes and why. Link the issue it closes, if there is one. -->

## Checklist

What each item means is in [CONTRIBUTING.md](https://github.com/ianderso/gov-gazetteer-mcp/blob/main/CONTRIBUTING.md#what-a-change-carries).

- [ ] A test that fails without this change.
- [ ] `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` pass.
- [ ] Tool descriptions are written for the model and fit under `DESCRIPTION_BUDGET`. Raising it takes a pull request of its own, saying why.
- [ ] Anything returning a parish or Standesamt says it is a lead to the register, not the record.
- [ ] Every result that names a GOV object carries its id and page address, and the credit to GOV and CompGen.
- [ ] Failures come back as an `error` result, not an exception.
- [ ] If a tool or parameter changed: `tests/fixtures/tool_schema.json` is regenerated and the README tables are updated.
- [ ] If this relies on how GOV answers: a recorded fixture, and what was observed and when in `docs/API-NOTES.md`.
- [ ] Fixtures name only neutral, well-known places: no one's family research.
- [ ] A `CHANGELOG.md` entry, if users will notice the change.
- [ ] Nothing here writes to GOV, calls it faster than once a second, or works around a bot check.
