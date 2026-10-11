# gov-gazetteer-mcp

[![CI](https://github.com/ianderso/gov-gazetteer-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/gov-gazetteer-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gov-gazetteer-mcp)](https://pypi.org/project/gov-gazetteer-mcp/)

<!-- mcp-name: io.github.ianderso/gov-gazetteer-mcp -->

An [MCP](https://modelcontextprotocol.io) server for **GOV, the
Geschichtliches Orts-Verzeichnis**: the historical gazetteer of the Verein für
Computergenealogie (CompGen), with about 1.2 million places, mostly in
Germany and the lands that were once German or Prussian. GOV dates
everything it records about a place: its names, what kind of place it was,
and every place that enclosed it, civil and ecclesiastical.

That makes it the tool for the question a genealogist asks of every German
village: **in the year of the event, which Kreis, province and state held
it, and which parish and Standesamt kept its registers?** A village in Posen
was Prussian until 1919 and Polish after 1920; a Pomeranian one was German
until 1945. A Kreis was renamed, an Amt dissolved, a parish merged. The
server reads GOV's public web service and answers for one year at a time,
and it gives the dated enclosures a genealogy program needs to build a place
tree that is right for every date.

It works the way a careful genealogist does. **A gazetteer entry is a finding
aid, not evidence.** GOV is edited by volunteers: a parish or Standesamt link
says which register to look in, and the register's own heading confirms it.
Every result credits GOV and CompGen and carries the address of each
object's page on GOV, because that page is what gets cited.

Nothing here writes anywhere, and nothing here keeps a family tree. It sits
well beside [familysearch-mcp](https://github.com/ianderso/familysearch-mcp),
whose place tools resolve a place by date but know no parishes or
Standesämter, and [us-places-mcp](https://github.com/ianderso/us-places-mcp),
its counterpart for American counties.

This is an independent project. It is not affiliated with, endorsed by, or
supported by the Verein für Computergenealogie.

## Tools

The server publishes six tools. All are read-only.

| Tool | Purpose |
| --- | --- |
| `gov_search` | Find places by name: GOV id, names, types, coordinates and current parents. `within` limits the search to what lies inside a Kreis, province or state at any date; `place_type` keeps villages, parishes, Standesämter and so on. |
| `gov_object` | One object in full: every name with its language and dates, every type with dates, coordinates, external ids, and each part-of, located-in and represents relation with its dates and GOV's source ids. `children` lists what lies inside it, such as a parish's villages. Takes a GOV id, a GOV page address, or an external id such as `geonames:2851465`. |
| `gov_place_at_date` | A place in one year: its name then and the civil chain above it to the state, each level with its type and the link's dates. Links GOV leaves undated, or attests only in another year, are marked. |
| `gov_registers` | The parish (by confession, where GOV records it) and the Standesamt that covered a place in one year, the bodies above each parish whose archive may hold the books, and the local court. Says plainly when GOV records no parish or no Standesamt. |
| `gov_enclosures` | Every dated enclosure of a place and of each civil place above it, shaped for a dated place tree: one entry per parent with its periods, current first, each with a `gramps_date` such as `from 1871-01-01 to 1937-03-31`, and a suggested Gramps place type. |
| `cache_status` | This session's requests to GOV, by operation, and cache use. Makes no request. |

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request.

**Without cloning.** `uvx` fetches it from PyPI and runs it in one step:

```bash
uvx gov-gazetteer-mcp
```

**From a clone**, which is what you want if you will change it:

```bash
git clone https://github.com/ianderso/gov-gazetteer-mcp
cd gov-gazetteer-mcp
uv sync
uv run gov-gazetteer-mcp   # stdio server, usually launched by the client
```

Either way the server speaks MCP over stdio, so you will normally let an MCP
client start it rather than run it by hand.

### Claude Desktop

```json
{
  "mcpServers": {
    "gov": {
      "command": "uvx",
      "args": ["gov-gazetteer-mcp"]
    }
  }
}
```

A desktop app does not always inherit your shell's `PATH`. If the server fails
to start because `uvx` cannot be found, give the full path that `which uvx`
prints as the `command`.

### Claude Code

```bash
claude mcp add gov -- uvx gov-gazetteer-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `GOV_GAZETTEER_CACHE_DIR` | Response cache directory. Default `~/.cache/gov-gazetteer-mcp`. |
| `GOV_GAZETTEER_TIMEOUT` | HTTP timeout in seconds for one request. Default 30. |
| `GOV_GAZETTEER_MIN_INTERVAL` | Least seconds between two requests to GOV. Default 1, and never below 1. |
| `GOV_GAZETTEER_CONTACT` | An email address or URL added to the User-Agent, so CompGen can reach you if your use causes trouble. Optional, and courteous. |

An unusable value is reported on the first tool call as a `not_configured`
result naming the variable. The server writes no files but its cache.

## Being a good guest

GOV is run by volunteers on CompGen's own server. The client sends one
request at a time, at least a second apart, and two identical calls in flight
share one request. Objects are cached for 30 days and searches for 7, and
every object an answer carries (a search returns whole objects, not ids) is
kept for the session, so a place already seen is not asked for again. A
question about one year reads each enclosing object once; the same place in
another year then costs nothing. A walk reads at most 40 objects per call and
says so if it stops. A 429, a 5xx or a dropped connection gets one retry,
honouring `Retry-After`; a SOAP fault is GOV's answer and is not retried. The
User-Agent names the package, its version and this repository.

### Terms of use

GOV's site has no terms-of-use page; its footer links CompGen's
[Impressum](https://compgen.de/impressum/) and
[privacy statement](https://compgen.de/datenschutz). The home page says the
project was started to make "qualitativ hochwertige Daten für jedermann
bereitzustellen" (to provide high-quality data for everyone,
[gov.genealogy.net](https://gov.genealogy.net/)), and it publishes its SOAP
services without a key at
[gov.genealogy.net/services](https://gov.genealogy.net/services/). CompGen
describes GOV's data as freely available Linked Open Data; GOV's documentation
on GenWiki sits behind a bot check and was not read for this project. Every
result credits "GOV — Geschichtliches Orts-Verzeichnis, Verein für
Computergenealogie (CompGen)" and links each object's page.

As a fact: GOV's `robots.txt` disallows a few website paths (edit and history
pages, KML and GeoJSON exports, the distance search) and names several
crawlers it shuts out entirely; it does not mention `/services/`, the web
service this server uses.

## How to read what comes back

- **Ask with the event's year.** `gov_place_at_date` and `gov_registers`
  answer for one year. A place that changed Kreis or state within that year
  shows both links with their dates; choose by the event's exact date.
- **A parish or Standesamt link is a lead.** GOV is edited by volunteers.
  Confirm the parish or office in the register itself, whose heading or title
  page names it and the places it served, and cite the register.
- **Certainty is marked.** A link is `dated` (its dates bracket the year),
  `undated` (GOV gives none; it is assumed to hold), or `attested in another
  year only` (GOV records it from one directory of another year). Prefer the
  first.
- **Where GOV links no parish to a place,** `gov_registers` gives the parishes
  whose church stands in the place, and says so: usually, not always, the
  place's own parish. **Where GOV links no Standesamt,** it gives a Standesamt
  of the same name in the same district, as a candidate, and says GOV does
  not link them. In well-modelled regions (Pomerania, for one) GOV links both
  directly.
- **Name search is literal.** It matches whole words and word beginnings,
  ignoring case and accents (`Lubeck` finds Lübeck), and never spelling
  variants: German, Polish and older spellings (Cöslin, Köslin, Koszalin) each
  need their own call. A zero covers only the spellings and area searched.
  GOV answers at most 500 objects per search.
- **Names follow the year.** A Polish name GOV dates from 1945 is not given
  for 1900. Among names that hold, `language` (`deu` by default, `pol` for a
  place under Polish rule) picks the one shown; `names_at_date` lists them all.
- **Before 1874 there was no Standesamt** in Prussia (1876 in the rest of the
  Empire; earlier on the left bank of the Rhine). `gov_registers` says so for
  those years.
- **Confederations are left out.** GOV records memberships of the German
  Confederation, the Rheinbund, the League of Nations, the EU and the UN as
  enclosures; they are not levels of government, so a chain stops below them
  and a note names them.
- **Cite the object's page.** Use the `citation` each result carries: the
  source credit, the entry's title, its GOV id and address, the day GOV last
  changed it and the day it was read.

## Deliberately not here

- **Editing GOV.** GOV's ChangeService needs an account; this server builds
  no envelope for it.
- **The GenWiki documentation.** It sits behind a bot check (Anubis), which
  this project does not work around. Everything here was built from the WSDLs
  and GOV's live answers; see [docs/API-NOTES.md](docs/API-NOTES.md).
- **Bulk export.** This server reads places one at a time for research, not
  whole regions.

## Security

Tool arguments are written by a model, and the model reads text this server
does not control, including GOV's own names and notes. The server assumes
that text can steer the model, and limits what a steered model can make it do.

- **One address.** Every request is a POST over https to
  `gov.genealogy.net/services/ComplexService`; a request hook refuses
  anything else, and an argument chooses only what is asked, never where.
  Redirects are not followed.
- **Read operations only.** The client builds envelopes for seven read
  operations and nothing else.
- **Public addresses only.** The connection goes to an address checked to be
  public, so a DNS answer pointing at a private network is refused. Proxy
  settings in the environment are not used.
- **Bounded, plain answers.** An answer over 10 MB is refused as it streams
  in, and one carrying a document type declaration is refused before it is
  parsed.
- **Arguments are validated** (GOV ids, external ids, years, type names)
  before they reach a request.
- **GOV's text is untrusted.** Names and notes reach the model verbatim. The
  server's instructions tell the model to treat that text as material to
  weigh, never as instructions; the model still decides, so review what it
  proposes to do.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches GOV
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # paced calls to GOV itself
```

The live check asks GOV what the recorded fixtures cannot: whether its
answers still have the shape the server reads. See
[CONTRIBUTING.md](CONTRIBUTING.md) for how the suite is organised,
[docs/API-NOTES.md](docs/API-NOTES.md) for what was observed of the service
and when, and [docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped
this way.

## Credits

The data is GOV's — Geschichtliches Orts-Verzeichnis, a project of the
[Verein für Computergenealogie e.V. (CompGen)](https://www.compgen.de/), built
by its volunteers. GOV's software is by Jesper Zedlitz.

## License

[MIT](LICENSE).
