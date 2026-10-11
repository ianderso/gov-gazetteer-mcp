"""Walking GOV's enclosures: the chain in a year, the registers, the dated hierarchy.

GOV records each relation on the enclosed object: a village is ``part-of``
its municipality, its parish, its Standesamt and its court, each with its own
dates. To know what a parent *is* the parent has to be read, so a walk reads
every parent whose relation may hold in the year asked about, follows the
civil and settlement ones upward, and keeps the rest (parishes, registry
offices, courts) for :func:`registers`. Every object read is cached for 30
days, so a second question about the same place, in any year, costs nothing.

Each walk is bounded: at most ``budget`` requests to GOV and ``MAX_DEPTH``
levels. A walk that reaches the bound returns what it has and says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import model
from .client import GovError, GovHttp
from .dates import ATTESTED_ELSEWHERE, OUTSIDE, RANK, UNDATED, Span

#: Most requests one tool call may send to GOV.
DEFAULT_BUDGET = 40

#: Most levels a chain climbs.
MAX_DEPTH = 15

#: Most alternative chains reported.
MAX_PATHS = 4

#: Most ecclesiastical levels above a parish reported.
MAX_SUPERIORS = 4

#: Most places a dated hierarchy lists.
MAX_PLACES = 40


@dataclass
class Link:
    """One relation from a child to a parent, judged for one year."""

    child: str
    parent: str
    relation: str
    span: Span
    validity: str
    role: str
    sources: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        """The link's relation, dates and how sure they make it."""
        out: dict[str, Any] = {"relation": self.relation, **self.span.describe()}
        out["certainty"] = model.certainty(self.validity)
        if self.sources:
            out["sources"] = self.sources
        return out


class Walk:
    """A bounded reader of GOV objects for one question.

    ``objects`` holds every object read, ``stored`` when each was fetched,
    and ``problems`` the parents that could not be read and why.
    """

    def __init__(self, http: GovHttp, *, budget: int = DEFAULT_BUDGET):
        self.http = http
        self.budget = budget
        self.objects: dict[str, dict] = {}
        self.stored: dict[str, float] = {}
        self.problems: list[dict[str, str]] = []
        self.exhausted = False
        self.failed: GovError | None = None
        self._start_calls = http.live_calls

    @property
    def requests(self) -> int:
        """int: Requests this walk sent to GOV."""
        return self.http.live_calls - self._start_calls

    async def start(self, gov_id: str, *, refresh: bool = False) -> dict:
        """Read the object a question is about. Its failure is the tool's failure.

        Raises
        ------
        GovError
            ``not_found`` if GOV has no such object, or any failure to read it.
        """
        obj, stored = await self.http.object(gov_id, refresh=refresh)
        self.objects[gov_id] = obj
        self.stored[gov_id] = stored
        return obj

    async def get(self, gov_id: str) -> dict | None:
        """Read a parent, within the budget. None if it cannot be read; the reason is kept."""
        if gov_id in self.objects:
            return self.objects[gov_id]
        if self.failed is not None or self.requests >= self.budget:
            peeked = self.http.peek(gov_id)
            if peeked is None:
                self.exhausted = self.exhausted or self.failed is None
                self.problems.append(
                    {
                        "gov_id": gov_id,
                        "reason": "not read: this call's request limit was reached"
                        if self.failed is None
                        else "not read: GOV stopped answering",
                    }
                )
                return None
            obj, stored = peeked
        else:
            try:
                obj, stored = await self.http.object(gov_id)
            except GovError as exc:
                if exc.code == "not_found":
                    self.problems.append(
                        {"gov_id": gov_id, "reason": "GOV links to it but has no such object"}
                    )
                else:
                    self.failed = exc
                    self.problems.append({"gov_id": gov_id, "reason": f"GOV failed: {exc.code}"})
                return None
        self.objects[gov_id] = obj
        self.stored[gov_id] = stored
        return obj

    async def links_at(self, child_id: str, year: int) -> list[Link]:
        """Every part-of and located-in link of a child that may hold in ``year``.

        A parent whose dated types all exclude the year is left out: GOV says
        it was not there then.
        """
        child = self.objects[child_id]
        out = []
        for kind in ("part-of", "located-in"):
            for rel in model.relations(child, kind):
                validity = rel["span"].validity(year)
                if validity == OUTSIDE:
                    continue
                parent = await self.get(rel["ref"])
                if parent is None or not model.existed(parent, year):
                    continue
                out.append(
                    Link(
                        child_id,
                        rel["ref"],
                        kind,
                        rel["span"],
                        validity,
                        model.role_at(parent, year),
                        rel.get("sources", []),
                    )
                )
        return out


@dataclass
class Climb:
    """The result of climbing from a place in one year."""

    year: int
    start: str
    links: dict[str, list[Link]] = field(default_factory=dict)  # every link read, by child
    chain_links: dict[str, list[Link]] = field(default_factory=dict)  # the ones followed
    order: list[str] = field(default_factory=list)  # chain nodes in the order reached

    def paths(self) -> list[list[Link]]:
        """Every chain from the start to a top, best first.

        Best means: the weakest link is as strong as possible, then the
        chain is as long as possible (so an Amt between a municipality and
        its Kreis is kept), then its links are strong overall.
        """
        found: list[list[Link]] = []

        def dfs(node: str, path: list[Link], seen: set[str]) -> None:
            if len(found) >= 64:
                return
            nexts = [lk for lk in self.chain_links.get(node, []) if lk.parent not in seen]
            if not nexts or len(path) >= MAX_DEPTH:
                found.append(list(path))
                return
            for lk in nexts:
                path.append(lk)
                seen.add(lk.parent)
                dfs(lk.parent, path, seen)
                seen.discard(lk.parent)
                path.pop()

        dfs(self.start, [], {self.start})

        def score(path: list[Link]) -> tuple:
            ranks = [RANK[lk.validity] for lk in path]
            return (min(ranks, default=3), len(path), sum(ranks))

        unique: dict[tuple[str, ...], list[Link]] = {}
        for path in sorted(found, key=score, reverse=True):
            unique.setdefault(tuple(lk.parent for lk in path), path)
        return list(unique.values())[:MAX_PATHS]

    def best(self) -> list[Link]:
        """The best chain (see :meth:`paths`); empty when the start has no parent."""
        paths = self.paths()
        return paths[0] if paths else []


async def climb(walk: Walk, start: str, year: int) -> Climb:
    """Climb the civil and settlement chain from ``start`` in ``year``.

    At each level every parent that may hold is read. Civil and settlement
    parents are followed: those whose links are dated or undated, or, when a
    level has none of those, the ones attested only in another year.
    """
    result = Climb(year, start)
    frontier, seen, depth = [start], {start}, 0
    while frontier and depth < MAX_DEPTH:
        following: list[str] = []
        for child in frontier:
            result.order.append(child)
            links = await walk.links_at(child, year)
            result.links[child] = links
            chain = [lk for lk in links if lk.role in model.CHAIN_ROLES]
            best = max((RANK[lk.validity] for lk in chain), default=0)
            floor = RANK[UNDATED] if best >= RANK[UNDATED] else RANK[ATTESTED_ELSEWHERE]
            follow = [lk for lk in chain if RANK[lk.validity] >= floor]
            result.chain_links[child] = follow
            for lk in follow:
                if lk.parent not in seen:
                    seen.add(lk.parent)
                    following.append(lk.parent)
        frontier, depth = following, depth + 1
    return result


async def superiors(walk: Walk, parish_id: str, year: int) -> list[tuple[dict, Link]]:
    """The ecclesiastical bodies above a parish in ``year``, nearest first.

    One path: at each level the best-evidenced ecclesiastical parent. These
    say whose archive is likely to hold the registers now.
    """
    out: list[tuple[dict, Link]] = []
    node, seen = parish_id, {parish_id}
    for _ in range(MAX_SUPERIORS):
        links = [
            lk
            for lk in await walk.links_at(node, year)
            if lk.role in ("parish", "church_district") and lk.parent not in seen
        ]
        if not links:
            break
        best = max(links, key=lambda lk: RANK[lk.validity])
        out.append((walk.objects[best.parent], best))
        seen.add(best.parent)
        node = best.parent
    return out


@dataclass
class Hierarchy:
    """Every civil and settlement place above a start, over a window of years."""

    places: list[str] = field(default_factory=list)
    enclosed_by: dict[str, list[dict]] = field(default_factory=dict)
    other_parents: list[dict] = field(default_factory=list)
    confederations: list[str] = field(default_factory=list)
    truncated: bool = False


async def hierarchy(walk: Walk, start: str, first: int | None, last: int | None) -> Hierarchy:
    """All dated enclosures of ``start`` and of the places above it, within a window.

    Breadth first, nearest places first, at most ``MAX_PLACES`` places.
    Parishes, courts and registry offices of the start are kept apart in
    ``other_parents``; confederations are left out and named.
    """
    result = Hierarchy()
    queue, seen = [start], {start}
    while queue:
        node = queue.pop(0)
        result.places.append(node)
        child = walk.objects[node]
        refs: list[dict] = []
        for kind in ("part-of", "located-in"):
            for rel in model.relations(child, kind):
                if not rel["span"].overlaps(first, last):
                    continue
                parent = await walk.get(rel["ref"])
                if parent is None:
                    continue
                role = _role_in_window(parent, first, last)
                entry = {
                    "parent": rel["ref"],
                    "relation": kind,
                    "span": rel["span"],
                    "sources": rel.get("sources", []),
                    "role": role,
                }
                if role == "confederation":
                    if rel["ref"] not in result.confederations:
                        result.confederations.append(rel["ref"])
                elif role in model.CHAIN_ROLES:
                    refs.append(entry)
                    if rel["ref"] not in seen:
                        if len(seen) >= MAX_PLACES:
                            result.truncated = True
                        else:
                            seen.add(rel["ref"])
                            queue.append(rel["ref"])
                elif node == start:
                    result.other_parents.append(entry)
        result.enclosed_by[node] = refs
    return result


def _role_in_window(obj: dict, first: int | None, last: int | None) -> str:
    """An object's role judged by the type that touches the window, the latest of them."""
    types = [
        t
        for t in model.entries(obj, "type")
        if t["value"].isdigit() and t["span"].overlaps(first, last)
    ] or [t for t in model.entries(obj, "type") if t["value"].isdigit()]
    if not types:
        return "other"
    roles = {model.role_of_type(int(t["value"])) for t in types}
    # A place that was ever civil or a settlement in the window is part of the chain.
    for role in ("confederation", "civil", "settlement"):
        if role in roles:
            return role
    latest = max(types, key=lambda t: t["span"].sort_end())
    return model.role_of_type(int(latest["value"]))
