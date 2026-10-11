"""GOV's dates, decoded, and the question "did this hold in year Y?".

GOV dates a name, a type or a relation in one of three ways (observed
2026-10-11; see docs/API-NOTES.md):

* a ``timespan`` with ``begin`` and/or ``end``, each a Julian Day Number
  (``jd``) and a ``precision``: 0 the year is known, 1 the month, 2 the day.
  A begin is the first day of its period and an end the last, so an end of
  31 December 2003 and a begin of 1 January 2004 meet without overlapping;
* ``begin-year`` and/or ``end-year`` attributes, whole years, inclusive;
* a lone ``year`` attribute: the fact is attested in that year (a census, a
  gazetteer of that year), not that it began or ended then.

Anything with none of these is undated: GOV gives no period for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The first Julian Day Number of the Gregorian calendar (15 October 1582).
#: Days before it are converted to the Julian calendar, as historians write them.
GREGORIAN_START_JD = 2299161

#: How a span bears on a year, best first.
DATED = "dated"  # its begin and end bracket the year (either may be open)
ATTESTED = "attested"  # GOV attests it in exactly that year
UNDATED = "undated"  # GOV gives no dates
ATTESTED_ELSEWHERE = "attested_elsewhere"  # attested only in another year
OUTSIDE = "outside"  # its dates exclude the year

#: Rank of each validity, for choosing between alternatives. Outside is 0.
RANK = {DATED: 3, ATTESTED: 3, UNDATED: 2, ATTESTED_ELSEWHERE: 1, OUTSIDE: 0}


@dataclass(frozen=True)
class GovDate:
    """One end of a span, as precise as GOV knows it."""

    year: int
    month: int | None = None
    day: int | None = None

    def iso(self) -> str:
        """``1937``, ``1937-04`` or ``1937-04-01``, as precise as recorded."""
        text = f"{self.year:04d}" if self.year >= 0 else str(self.year)
        if self.month is not None:
            text += f"-{self.month:02d}"
            if self.day is not None:
                text += f"-{self.day:02d}"
        return text


def jd_to_ymd(jd: int) -> tuple[int, int, int]:
    """The calendar date of a Julian Day Number: Gregorian from 1582-10-15, Julian before."""
    if jd >= GREGORIAN_START_JD:
        # Fliegel and Van Flandern (1968), for the Gregorian calendar.
        ell = jd + 68569
        n = 4 * ell // 146097
        ell -= (146097 * n + 3) // 4
        i = 4000 * (ell + 1) // 1461001
        ell -= 1461 * i // 4 - 31
        j = 80 * ell // 2447
        day = ell - 2447 * j // 80
        ell = j // 11
        month = j + 2 - 12 * ell
        year = 100 * (n - 49) + i + ell
        return year, month, day
    c = jd + 32082
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = d - 4800 + m // 10
    return year, month, day


def from_jd(jd: int, precision: int) -> GovDate:
    """A GovDate at GOV's precision: 0 year, 1 month, 2 day."""
    year, month, day = jd_to_ymd(jd)
    if precision <= 0:
        return GovDate(year)
    if precision == 1:
        return GovDate(year, month)
    return GovDate(year, month, day)


@dataclass(frozen=True)
class Span:
    """When a name, type or relation held, as GOV records it."""

    begin: GovDate | None = None
    end: GovDate | None = None
    attested: int | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> Span:
        """Build from the cached form :func:`gov_gazetteer_mcp.soap` stores.

        A timespan end wins over an ``end-year`` attribute, and so for the begin.
        """
        raw = raw or {}
        begin = end = None
        if (b := raw.get("begin")) is not None:
            begin = from_jd(int(b[0]), int(b[1]))
        elif (by := raw.get("begin_year")) is not None:
            begin = GovDate(int(by))
        if (e := raw.get("end")) is not None:
            end = from_jd(int(e[0]), int(e[1]))
        elif (ey := raw.get("end_year")) is not None:
            end = GovDate(int(ey))
        attested = raw.get("year")
        return cls(begin, end, int(attested) if attested is not None else None)

    @property
    def undated(self) -> bool:
        """bool: GOV gives no dates at all."""
        return self.begin is None and self.end is None and self.attested is None

    def validity(self, year: int) -> str:
        """How this span bears on ``year``: one of the validity constants above."""
        if self.begin is None and self.end is None:
            if self.attested is None:
                return UNDATED
            return ATTESTED if self.attested == year else ATTESTED_ELSEWHERE
        if self.begin is not None and year < self.begin.year:
            return OUTSIDE
        if self.end is not None and year > self.end.year:
            return OUTSIDE
        return DATED

    def overlaps(self, first: int | None, last: int | None) -> bool:
        """Whether the span touches the years ``first`` to ``last`` (either open).

        An undated span touches every window; an attested year must fall in it.
        """
        if self.begin is None and self.end is None:
            if self.attested is None:
                return True
            return (first is None or self.attested >= first) and (
                last is None or self.attested <= last
            )
        if last is not None and self.begin is not None and self.begin.year > last:
            return False
        return not (first is not None and self.end is not None and self.end.year < first)

    def sort_end(self) -> float:
        """A key that puts an open-ended (current) span first, then the latest end."""
        if self.end is None and self.attested is None:
            return float("inf")
        if self.end is not None:
            return self.end.year + (self.end.month or 12) / 100
        return float(self.attested or 0)

    def describe(self) -> dict[str, Any]:
        """The span for a result: ``from``, ``to``, ``attested`` and a ``gramps_date``.

        Keys with no value are left out; an undated span says so.
        """
        out: dict[str, Any] = {}
        if self.begin is not None:
            out["from"] = self.begin.iso()
        if self.end is not None:
            out["to"] = self.end.iso()
        if self.attested is not None and self.begin is None and self.end is None:
            out["attested"] = self.attested
        if self.undated:
            out["undated"] = True
        if text := self.gramps_date():
            out["gramps_date"] = text
        return out

    def gramps_date(self) -> str:
        """The span in the date syntax Gramps 5.2 and later parse.

        ``from 1871-01-01 to 1937-03-31``, ``from 1937-04-01``, ``to 1945``,
        a bare ``1885`` for a year it is only attested in, and nothing when
        undated.
        """
        if self.begin is not None and self.end is not None:
            return f"from {self.begin.iso()} to {self.end.iso()}"
        if self.begin is not None:
            return f"from {self.begin.iso()}"
        if self.end is not None:
            return f"to {self.end.iso()}"
        if self.attested is not None:
            return str(self.attested)
        return ""
