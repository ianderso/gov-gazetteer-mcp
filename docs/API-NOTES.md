# GOV web service notes

What GOV's SOAP services actually do, observed against the live service.
GOV's own documentation is on GenWiki, which sits behind a bot check (Anubis)
and was not read; everything here comes from the WSDLs, GOV's own web pages
(its type list and a few item pages) and live answers.

Observed 2026-10-11, about 200 requests in all, at least a second apart, with
the User-Agent `gov-gazetteer-mcp/0.1.0 (+https://github.com/ianderso/gov-gazetteer-mcp)`.

## Transport

- `https://gov.genealogy.net/services/` lists three Apache CXF services:
  **ChangeService** (`saveSource`, `saveObject`, `merge`: editing, needs an
  account, never called here), **ComplexService** and **SimpleService**. The
  last two offer the same read operations; SimpleService answers with bare
  ids, ComplexService with whole objects.
- WSDL at `<endpoint>?wsdl`. SOAP 1.1, `style="rpc"`, `use="literal"`, body
  namespace `http://gov.genealogy.net/ws`, `soapAction=""`. Parts are
  unqualified children of `ws:<operation>`; an `ArrayOfInt` is a sequence of
  qualified `ws:int`, an `ArrayOfString` of `ws:item`.
- The answer is `ns1:<operation>Response` holding one unqualified `out`. For
  `getObject` the `out` element *is* the object (its `id` attribute and
  children in `http://gov.genealogy.net/data`); for searches and
  `getChildObjects` it holds `ns2:object` elements; for `getTypeDescription`
  `ns3:item` strings.
- No key, no cookie. Served by Caddy; answers are gzip-compressed when asked.
  Response times 0.5 to 1.1 s for objects and small searches, 2.6 s for a
  search of 117 objects (82 KB).
- No rate limit is published and none was met.
- `robots.txt` disallows `/item/editQuicktext/`, `/item/history/`,
  `/item/reindex/`, `/item/geoJson/`, two `/recentChanges/` paths,
  `/genwiki/gallery/`, `/kml/` and `/search/distanceSearch/`, and shuts out
  several named crawlers entirely. It does not mention `/services/`.
- GOV's site has no terms-of-use page. The footer links CompGen's Impressum
  and privacy statement at compgen.de.

## Faults come with 404 or 500

| Situation | Answer |
| --- | --- |
| `getObject` of an id that does not exist | **404**, `soap:Fault`, `faultstring` "There is no item with id 'X'.", detail `ns1:NoSuchObject` |
| `getObjectByExternalId` with no such reference | **404**, fault, detail `NoSuchReference` |
| `getTypeDescription` of an unknown type | **404**, fault, detail `UnknownType` |
| `searchByNameAndType` with a non-numeric type | **500**, fault `soap:Server`, "For input string: \"xyz\"", no detail |
| A malformed number in any part | **500**, fault `soap:Client`, "Unmarshalling Error: Not a number" |
| `checkObjectId` of an unknown id | 200, empty `out` |

So a 5xx is not necessarily an outage: the client parses the body for a
fault first, and only retries a 5xx that carries none.

## Objects

An object (`ns2:object`, or `out` itself) carries:

- attributes `id`, `last-modification` (ISO date-time), sometimes `deprecated`;
- at most one `position` (`lat`, `lon`, optional `height`, and `type`);
- dated **properties**, each an element with `value` and optional `lang`:
  `name`, `type` (a type id), `external-reference` (`system:ref`, e.g.
  `geonames:2851465`, `wikidata:Q40623`, `opengeodb:22697`, `SIMC:0977278`,
  `NUTS2003:DEE38`, `Kreisnummer:0813`), `url`, `population`, `postal-code`,
  `municipal-id`, `area`, `households`, `buildings`, `w-number`,
  `denomination`;
- dated **relations**, each with a `ref` to another object: `part-of`
  (hierarchy: civil, church, court and Standesamt alike), `located-in` (a
  building in a place) and `represents` (a church building representing its
  parish);
- `note` elements with free text and a `lang`, written by volunteers;
- `source` children on properties and relations, each a `ref` to a source
  object (`source_<n>`, shown at `https://gov.genealogy.net/item/show/source_<n>`),
  sometimes with a page.

A search answer holds **whole** objects, identical to what `getObject`
returns for the same id (compared for `object_289891`).

### Dates

Three forms, on any property or relation:

- `<timespan><begin jd=".." precision=".."/><end .../></timespan>`. `jd` is a
  Julian Day Number. `precision` 0 is a year, 1 a month, 2 a day: a year's
  begin is 1 January and its end 31 December; a month's end is its last day.
  Checked against known events: 2342355 p2 is 18 January 1701 (the Prussian
  coronation), 2404429 p2 is 1 January 1871, 2402838 p2 is 24 August 1866 (the
  German Confederation's end), 2427255 p1 is July 1933. An end of
  2453005 (31 December 2003) meets a begin of 2453006 (1 January 2004).
- `begin-year` and `end-year` attributes, whole years.
- A lone `year` attribute: attested in that year (seen with 1883, 1885, 1887
  and 1888, each tied to one source).

A relation with none of these is undated; many are.

### Position types

As GOV's item pages label them: `p` a recorded position (no qualifier shown),
`c` "berechneter Mittelpunkt des Objekts" (computed centre), `e` "geschätzt"
(estimated), `l` "Position des Ortes, an dem sich das Objekt befindet" (the
position of the place the object stands in).

### Confession codes

As GOV's item pages label them: `ev` evangelisch, `lu` lutherisch, `lt`
evangelisch-lutherisch, `rf` reformiert, `rk` römisch-katholisch, `ak`
alt-katholisch. Others are passed through as they are.

### Types

`https://gov.genealogy.net/type/list` lists all 276 types with id, group
("Typgruppe"), name and three flags. Groups: (politische) Verwaltung 174,
Wohnplatz 37, Kirche 35, Gericht 10, Sonstige 10, Zivilverwaltung 4, Platz 3,
geographische Typen 2, Verkehrswesen 1. `getTypeDescription(id, "deu")`
answers `[name, group]` but with different group words ("Stadt",
"Siedlung" for type 51); in English the group is empty ("town", "").

## Operations this server calls

### `searchByName(placename)`

- **Not exact-match.** Words match at their beginnings (`Quedlin` finds the
  24 Quedlinburg objects), case and accents are ignored (`Lübeck` finds
  "Lubeck, West Virginia"), every word given must match (`Quedlinburg Dom`
  finds 2). No infix (`edlinburg` finds nothing) and no fuzziness
  (`Quedlinbrug` finds nothing).
- **Capped at 500 objects** (`Nikolaus` returned exactly 500, 285 KB).
- Results come in no useful order (by last modification, it seems).

### `searchByNameAndType(placename, types)`

`types` is a comma-separated list of type ids (`51,29`). The same matching.
A non-numeric entry is a 500 fault.

### `searchDescendantsByName(parentId, childName)`

Objects inside the parent at any date, through any part-of chain: inside
Kreis Göttingen, `Nikolausberg` finds the settlement, its old municipality,
its church building and the 1883 Standesamt, but not its Kirchspiel, which
belongs to the church hierarchy only.

### `getObject(itemId)`, `getObjectByExternalId(system, ref)`

One whole object. External lookups work for `geonames` and `wikidata` at
least (`geonames:2851465` and `wikidata:Q40623` both name Quedlinburg
objects).

### `getChildObjects(itemId)`

Whole objects whose `part-of`, `located-in` or `represents` points at the
item: a Kirchspiel's children include the church building that represents it.

### `getTypeDescription(typeId, language)`

Used only for a type missing from the shipped table.

## Operations not used, and why

- `getParentObjectWithTypeAtDate(childId, interestingTypes, julianDate)`:
  walks upward on the server and returns the nearest ancestor(s) of the given
  types at the date (from Nikolausberg, asking for Kreis types, it returns
  Kreis Göttingen two levels up; asking for every civil type it returns only
  the municipality). Its handling of undated and year-attested relations
  could not be pinned down: a relation attested in 1885 counted for 1888 but
  a Kirchspiel attested in 1888 did not count for 1900. The server judges
  dates itself instead; see DESIGN.
- `getNameAtDate(itemId, julianDate, preferredLanguage)`: for Köslin it
  answered "Köslin" for both 1900 and 1950 when asked in German, and
  "Koszalin" for both when asked in Polish; it does not choose by who held
  the place. The server's own choice is no better informed, but it never
  gives a name whose dates exclude the year, and it lists every name that
  holds.
- `searchByBoundingBox`, `searchDescendantsByType*`, `lookupObject`,
  `listTopLevelObjects`, `checkObjectId`, `searchRelatedByName`, `getSource`,
  `getPositions`, `getRecordsForObject`, `searchDescendantsByNameLanguage`:
  not needed by the five questions the tools answer.

## How well places are linked

Varies by region, which is why `gov_registers` has labelled fallbacks:

- **Pomerania** (Stolp, now Słupsk; Köslin, now Koszalin): the settlement
  and its municipality are `part-of` the Standesamt and the parishes of both
  confessions directly, mostly dated `to 1945` or attested in 1885 or 1888.
- **Province of Hanover** (Nikolausberg near Göttingen) and **Province of
  Saxony** (Quedlinburg): no link from a place to its parish; the parish is
  found through the church building `located-in` the place that
  `represents` it. The Standesamt exists as an object `part-of` the Kreis,
  attested 1883, with no link to the places it served.
- **Lübeck**: the city is linked to a Catholic Pfarrkuratie without dates;
  the Stadtkreis to an Old Catholic congregation; no Standesamt object.

## The website

- An object's page is `https://gov.genealogy.net/item/show/<id>`; its Linked
  Data identifier, shown on the page as "GOV-Kennung", is
  `http://gov.genealogy.net/<id>`.
- The home page gives about 1.2 million entries "mit Schwerpunkt Europa,
  Nordamerika und Australien" as of November 2024, and names
  gov@genealogy.net for the administrators and
  https://discourse.genealogy.net/c/gov-develop/ for technical questions.
