# Design

Why the server is shaped the way it is, and what is out of scope by decision.

## The question it answers

"In the year of this baptism, where was the village, and whose register is
it in?" For a German or once-Prussian place the answer moves: the Kreis is
renamed, the province is redrawn, the state changes in 1866, 1871, 1919-20 or
1945, the parish is merged, the Standesamt is created in 1874. GOV records
all of that, dated, for about 1.2 million places. FamilySearch's gazetteer
resolves a place by date too, but knows no parishes and no Standesämter;
that is GOV's particular value, and `gov_registers` is built around it.

## Four questions, five tools

- **Which object?** `gov_search`, by name, optionally inside a Kreis or
  province and of given types. GOV's search is literal, so the description
  tells the model to try each spelling.
- **What does GOV say about it?** `gov_object`, everything, decoded.
- **What was it in year Y?** `gov_place_at_date`, the name and civil chain.
- **Whose registers?** `gov_registers`, parish, Standesamt, court.
- **The whole dated hierarchy**, for a place tree: `gov_enclosures`.

The year is an argument rather than a date because events are usually known
by year first. When a place changed parent within the year, both links come
back with their dates, and a note says to choose by the event's exact date.

## Why a local walk, not GOV's date service

GOV offers `getParentObjectWithTypeAtDate`, which walks upward on the server
and returns the nearest ancestor of given types at a date. It would save
requests, but its date logic is not documented where this project can read
it, and probing it showed choices that cannot be explained from the data (a
relation attested only in 1885 counted for 1888 but not for 1900). The
server instead reads each object with `getObject` and judges every relation
itself, by rules it can state:

- A relation holds in year Y when its begin and end bracket Y (either may be
  open). Precision is honoured: an end of 31 March 1937 and a begin of 1 April
  1937 both hold "in 1937", which is exactly the case the boundary note
  covers.
- A relation with no dates is assumed to hold and is marked `undated`.
- A relation GOV attests in one year only (a lone `year` attribute, typically
  from one gazetteer or census) is marked `attested in another year only`
  when Y differs, and is used for the chain only when a level has nothing
  better.
- A parent whose types are all dated and none covers Y did not exist then,
  and is left out, whatever the relation says.

These rules are transparent in the output: every link carries its dates and
its certainty, so the caller sees why a level is there.

The cost is requests: a walk reads every parent whose relation may hold in Y,
civil or not, because a parent's role is known only once it is read. The
parishes, Standesämter and courts read that way are exactly what
`gov_registers` needs, and every object is cached for 30 days by id, so the
same place asked about in another year, or another tool, costs nothing. A
walk is capped at 40 requests and says so when it stops.

## Roles from GOV's own type groups

GOV publishes its 276 object types with a group for each (civil
administration, settlement, church, court, civil office and so on). The
server ships that table and derives a role: `civil` and `settlement` parents
make the chain; `parish` (Kirchspiel, Pfarrei, Kirchengemeinde, Pfarrkuratie,
Filiale and the like), `registry` (Standesamt), `court` and `church_district`
(Kirchenkreis, Dekanat, Bistum, Landeskirche) feed the registers;
`church_building` objects are used only to find a parish when GOV links none.

GOV's "Staatenbund" type (the German Confederation, the Rheinbund, the League
of Nations, the EU, the UN) is a membership, not a level of government; a
chain stops below it, and a note names it.

## Choosing one chain

A place can be part of several civil objects in one year: a municipality and
an Amt, or a municipality that is part of both its Kreis and its
Regierungsbezirk directly. The best chain is the one whose weakest link is
strongest, then the longest (so an intermediate Amt is kept), then the one
whose links are strongest overall. Every other civil parent read on the way
is listed under `also_enclosed_by`, so nothing GOV says is hidden.

## Registers: what GOV records, and what it does not

Parish and Standesamt links can sit on the place itself, on its
municipality, or higher: an Old Catholic congregation, say, covers a whole
Kreis. `gov_registers` gathers them from every level of the chain, nearest
first, and says which level carried each (`linked_via`). For each parish it
climbs the ecclesiastical bodies above it, because those say whose archive
holds the books now.

How completely GOV links places to parishes and Standesämter varies by
region. In Pomerania both are commonly linked directly. Elsewhere (the
Hanoverian and Saxon examples in the fixtures) a village's parish is recorded
only as the parish its church building represents, and the Standesamt only
as an office of the same name in the Kreis, attested in 1883. The tool
offers both as labelled fallbacks, and says plainly when there is nothing at
all. It never presents a fallback as GOV's link.

Before civil registration (1 October 1874 in Prussia, 1 January 1876 in the
rest of the Empire) the tool says so, and that a Standesamt link with no
start date does not mean the office existed.

## Names

GOV dates names unevenly: a German name may be dated to 1945 and a Polish one
from 1945, or both may be undated, or one may be attested from a single
directory. A name whose dates exclude the year is never given for it. Among
the rest, the language asked for comes first (German by default; `pol` for a
place under Polish rule), then the best evidenced. Every name that holds is
listed with its language.

## Shape for a place tree

`gov_enclosures` walks every civil and settlement parent over all time, or a
window of years, and gives each place its enclosures grouped by parent, the
current or last first, as the Gramps model wants (the first enclosure drives
the title). Each period carries a `gramps_date` in the syntax Gramps 5.2
parses (`from 1871-01-01 to 1937-03-31`, `from 1937-04-01`, `to 1945`, or a
bare year for an attestation). A suggested Gramps place type comes from GOV's
type: Kreis-level types are given as County, which is how a family tree that
also holds American counties will want them.

## SOAP by hand

GOV's services are SOAP 1.1, RPC style with literal parts. The seven read
operations the server needs take strings, integers and integer lists, and
answer with a handful of element types. A SOAP library (zeep) would add a
dependency tree and a WSDL fetch at start-up for no gain; the envelopes are
built as strings with every value XML-escaped, and answers are read with the
standard library's parser after refusing any document type declaration.
ComplexService is used rather than SimpleService because it returns whole
objects: a search's results, or a parish's child objects, need no further
requests.

## Courtesy

GOV is run by volunteers on CompGen's server. One request at a time, at least
a second apart (configurable upward only), identical calls in flight joined,
objects cached 30 days and searches 7, every object an answer carries kept
for the session, walks capped at 40 requests, one retry on 429 or a 5xx that
carries no SOAP fault (a fault is GOV's answer), none on a timeout. The
User-Agent names the package, its version and this repository, and
`GOV_GAZETTEER_CONTACT` adds the operator's address.

## Out of scope, by decision

- **Editing GOV.** The ChangeService needs an account and has no envelope
  here.
- **Working around bot checks.** GenWiki's documentation sits behind Anubis
  and was not read; should GOV's services ever answer with a challenge, the
  server reports `blocked` and stops.
- **Bulk harvesting.** The server reads places one at a time for research.
- **Choosing for the researcher.** Where GOV is ambiguous (two parents in a
  year, a fallback parish), the server shows both and says why, rather than
  picking silently.

## Tests

- Everything is mocked with respx against **recorded** answers
  (`tests/fixtures/`, one file per request, neutral well-known places only).
  The suite never touches GOV.
- Contract tests pin the tool surface as a client sees it: names and
  parameters (snapshot), descriptions present, dedented and within a size
  budget, the pitfalls present in the descriptions and instructions,
  annotations, no tool that raises when GOV fails, unknown parameters refused.
- `tests/test_security.py` takes the attacker's side: a request aimed
  elsewhere, a name that leads to a private address, an answer too large, an
  answer with entity declarations, an argument that tries to choose the host.
- `tests/live_check.py` asks GOV itself, by hand.
