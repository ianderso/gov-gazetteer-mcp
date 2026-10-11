# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

## [0.1.0] — 2026-10-11

First release.

### Added

- Six read-only tools over GOV's ComplexService SOAP web service:
  `gov_search`, `gov_object`, `gov_place_at_date`, `gov_registers`,
  `gov_enclosures` and `cache_status`.
- `gov_place_at_date`: a place's name and civil chain in one year, each level
  with its type and the link's dates, links marked dated, undated or attested
  in another year only, and a note when a place changed parent within the
  year.
- `gov_registers`: the parish (filtered by confession where asked) and the
  Standesamt linked to a place or any level above it in one year, the
  ecclesiastical bodies above each parish, and the local court. Where GOV
  links no parish, the parishes whose church stands in the place; where it
  links no Standesamt, one of the same name in the same district; both
  labelled as such. Says plainly when a level is missing, and that civil
  registration began in 1874 (Prussia) and 1876 (the rest of the Empire).
- `gov_enclosures`: every dated enclosure of a place and of each civil place
  above it, grouped by parent, current first, with Gramps 5.2 date strings
  and a suggested Gramps place type.
- GOV's 276 object types shipped as a table, with English groups and glosses
  for the common ones; a type GOV adds later is described live.
- Every result credits "GOV — Geschichtliches Orts-Verzeichnis, Verein für
  Computergenealogie (CompGen)" and gives each object's page on GOV; the
  citation carries the day GOV last changed the entry and the day it was read.
- A polite client: one fixed endpoint, read operations only, one request at a
  time at least a second apart (never less), identical calls joined, objects
  cached 30 days and searches 7, every object an answer carries reused for the
  session, at most 40 requests per walk, one retry on 429 and 5xx, SOAP
  faults not retried.
- Every connection checked where it is made (public addresses only), answers
  capped at 10 MB as they stream, and documents with a type declaration
  refused before parsing.
