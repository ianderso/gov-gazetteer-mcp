"""GOV's dates: Julian Day Numbers, precision, and whether a span holds in a year."""

from __future__ import annotations

import pytest

from gov_gazetteer_mcp.dates import (
    ATTESTED,
    ATTESTED_ELSEWHERE,
    DATED,
    OUTSIDE,
    UNDATED,
    GovDate,
    Span,
    from_jd,
    jd_to_ymd,
)


@pytest.mark.parametrize(
    ("jd", "ymd"),
    [
        (2451545, (2000, 1, 1)),
        (2342355, (1701, 1, 18)),  # the Prussian coronation, as GOV dates the kingdom
        (2404429, (1871, 1, 1)),  # the German Empire
        (2453005, (2003, 12, 31)),  # an end ...
        (2453006, (2004, 1, 1)),  # ... and the next begin
        (2299161, (1582, 10, 15)),  # the first Gregorian day
        (2299160, (1582, 10, 4)),  # the last Julian one
    ],
)
def test_julian_day_numbers_become_calendar_dates(jd, ymd):
    assert jd_to_ymd(jd) == ymd


def test_precision_says_how_much_of_the_date_is_known():
    assert from_jd(2428625, 0).iso() == "1937"
    assert from_jd(2427255, 1).iso() == "1933-07"
    assert from_jd(2428625, 2).iso() == "1937-04-01"


def test_a_timespan_wins_over_year_attributes():
    span = Span.from_raw({"begin": [2428625, 2], "begin_year": 1900, "end_year": 1950})
    assert span.begin == GovDate(1937, 4, 1) and span.end == GovDate(1950)


@pytest.mark.parametrize(
    ("raw", "year", "validity"),
    [
        ({}, 1900, UNDATED),
        ({"year": 1885}, 1885, ATTESTED),
        ({"year": 1885}, 1900, ATTESTED_ELSEWHERE),
        ({"begin_year": 1871}, 1900, DATED),
        ({"begin_year": 1871}, 1870, OUTSIDE),
        ({"end_year": 1945}, 1945, DATED),
        ({"end_year": 1945}, 1946, OUTSIDE),
        ({"begin": [2428625, 2], "end": [2431611, 2]}, 1937, DATED),
    ],
)
def test_validity_for_a_year(raw, year, validity):
    assert Span.from_raw(raw).validity(year) == validity


def test_a_window_touches_open_and_undated_spans():
    assert Span().overlaps(1800, 1900)
    assert Span.from_raw({"end_year": 1813}).overlaps(None, 1945)
    assert not Span.from_raw({"begin_year": 1964}).overlaps(None, 1945)
    assert not Span.from_raw({"year": 1883}).overlaps(1900, None)


def test_spans_describe_themselves_for_gramps():
    assert Span.from_raw({"begin": [2404429, 2], "end": [2428624, 2]}).describe() == {
        "from": "1871-01-01",
        "to": "1937-03-31",
        "gramps_date": "from 1871-01-01 to 1937-03-31",
    }
    assert Span.from_raw({"begin_year": 1937}).gramps_date() == "from 1937"
    assert Span.from_raw({"end_year": 1945}).gramps_date() == "to 1945"
    assert Span.from_raw({"year": 1885}).describe() == {"attested": 1885, "gramps_date": "1885"}
    assert Span().describe() == {"undated": True}


def test_current_spans_sort_first():
    spans = [Span.from_raw({"end_year": 1937}), Span(), Span.from_raw({"end_year": 1964})]
    spans.sort(key=Span.sort_end, reverse=True)
    assert spans[0].undated and spans[1].end == GovDate(1964)
