#!/usr/bin/env python

"""Compare two EnergyPlus HTML table output files.

usage:
    python TableDiff <in_file1> <in_file2> <out_abs_diff> <out_rel_diff> <err_log> <my_summary_file>

    <in_file1> = first input HTML file
    <in_file2> = second input HTML file
    <out_abs_file> = output HTML file of absolute differences
    <out_rel_file> = output HTML file of relative differences
    <out_err_log> = output HTML file of summary difference information
    <my_summary_file> = An overview (csv) of summary results, intended for multiple files appended
"""

# Copyright (C) 2009, 2010 Santosh Philip and Amir Roth 2013
# This file is part of tablediff.
#
# tablediff is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# tablediff is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with tablediff.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import getopt
import os
from pathlib import Path
import sys
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from energyplus_regressions.diffs.thresh_dict import ThreshDict

__author__ = "Santosh Philip (santosh_philip at yahoo dot com) and Amir Roth (amir dot roth at ee dot doe dot gov)"
__version__ = "1.4"
__copyright__ = "Copyright (c) 2009 Santosh Philip and Amir Roth 2013"
__license__ = "GNU General Public License Version 3"

this_file = Path(__file__).resolve()
script_dir = this_file.parent

title_css = """<!DOCTYPE html PUBLIC "-
//W3C//DTD XHTML 1.0 Strict//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"><html xmlns="http://www.w3.org/1999/xhtml">
<head><title>%s</title>  <style type="text/css"> %s </style>
<meta name="generator" content="BBEdit 8.2" /></head>
<body></body></html>
"""

the_css = """td.big {
    background-color: #FF969D;
}

td.small {
    background-color: #FFBE84;
}

td.equal {
    background-color: #CBFFFF;
}

td.table_size_error {
    background-color: #FCFF97;
}
td.stringdiff {
    background-color: #F6D8AE;
}
td.reordered {
    background-color: #DDEEFF;
}
.big {
    background-color: #FF969D;
}

.small {
    background-color: #FFBE84;
}

.stringdiff {
    background-color: #F6D8AE;
}
.reordered {
    background-color: #DDEEFF;
}

"""

DIFF_BIG = "big"
DIFF_EQUAL = "equal"
DIFF_REORDERED = "reordered"
DIFF_SMALL = "small"
DIFF_STRING = "stringdiff"
FIELD_DUMMY = "DummyPlaceholder"
FIELD_SUBCATEGORY = "Subcategory"
TABLE_SIZE_ERROR = "table_size_error"
SUMMARY_HEADER = (
    "Case,TableCount,BigDiffCount,SmallDiffCount,EqualCount,"
    "StringDiffCount,SizeErrorCount,NotIn1Count,NotIn2Count,ReorderedTableCount\n"
)
SKIPPABLE_TABLE_KEYS = ("Object Count Summary_Entire Facility_Input Fields",)

DiffValue = tuple[float | str, float | str, str]
DisplayValue = Any


@dataclass
class DiffCounts:
    small: int = 0
    big: int = 0
    equal: int = 0
    string: int = 0
    size_error: int = 0
    not_in_1: int = 0
    not_in_2: int = 0
    reordered: int = 0

    def add(self, other: "DiffCounts") -> None:
        self.small += other.small
        self.big += other.big
        self.equal += other.equal
        self.string += other.string
        self.size_error += other.size_error
        self.not_in_1 += other.not_in_1
        self.not_in_2 += other.not_in_2
        self.reordered += other.reordered

    def add_diff_type(self, diff_type: str) -> None:
        if diff_type == DIFF_SMALL:
            self.small += 1
        elif diff_type == DIFF_BIG:
            self.big += 1
        elif diff_type == DIFF_EQUAL:
            self.equal += 1
        elif diff_type == DIFF_STRING:
            self.string += 1

    def has_reportable_diff(self) -> bool:
        return self.small > 0 or self.big > 0 or self.string > 0


@dataclass
class TableComparison:
    counts: DiffCounts
    diff_dict: dict[str, list[DisplayValue]]
    horder: list[str]
    horder2: list[str]
    thresholds: dict[str, tuple[float, float]]
    reordered: bool = False


def _empty_result(message: str) -> tuple[str, int, int, int, int, int, int, int, int, int]:
    return message, 0, 0, 0, 0, 0, 0, 0, 0, 0


def _result_tuple(
    message: str,
    table_count: int,
    counts: DiffCounts,
) -> tuple[str, int, int, int, int, int, int, int, int, int]:
    return (
        message,
        table_count,
        counts.big,
        counts.small,
        counts.equal,
        counts.string,
        counts.size_error,
        counts.not_in_1,
        counts.not_in_2,
        counts.reordered,
    )


def _new_soup(title: str) -> BeautifulSoup:
    return BeautifulSoup(title_css % (title, the_css), features="html.parser")


def _append_text_cell(
    soup: BeautifulSoup,
    row: Tag,
    name: str,
    text: DisplayValue = "",
    css_class: str | None = None,
) -> Tag:
    attrs = {"class": css_class} if css_class else None
    cell = Tag(soup, name=name, attrs=attrs)
    cell.append(str(text))
    row.append(cell)
    return cell


def _read_html(path: Path) -> str:
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8", errors="ignore")


def _write_html(path: str, soup: BeautifulSoup) -> None:
    with open(path, "wb") as handle:
        handle.write(soup.prettify().encode("utf-8", errors="ignore"))


def thresh_abs_rel_diff(abs_thresh: float, rel_thresh: float, x: str, y: str) -> DiffValue:
    if x == y:
        return 0, 0, DIFF_EQUAL

    try:
        fx = float(x)
        fy = float(y)
    except ValueError:
        if x.strip() == y.strip():
            return 0, 0, DIFF_EQUAL
        return f"{x} vs {y}", f"{x} vs {y}", DIFF_STRING

    if fx == fy:
        return 0, 0, DIFF_EQUAL

    abs_diff = abs(fx - fy)
    rel_diff = abs((fx - fy) / fx) if abs(fx) > abs(fy) else abs((fy - fx) / fy)

    diff = DIFF_EQUAL
    if abs_diff > abs_thresh and rel_diff > rel_thresh:
        diff = DIFF_BIG
    elif (0 < abs_diff <= abs_thresh) or (0 < rel_diff <= rel_thresh):
        diff = DIFF_SMALL
    return abs_diff, rel_diff, diff


def prev_sib(entity):
    """Return the previous sibling, skipping blank navigable strings."""
    previous = entity
    while True:
        previous = previous.previous_sibling
        if isinstance(previous, NavigableString) and previous.strip() == "":
            continue
        return previous


def get_table_unique_heading(table):
    """Return the table unique name, which should be in a comment immediately before the table."""
    try:
        heading = prev_sib(table)
        return f"{heading}" if heading else None
    except Exception:  # pragma: no cover - BeautifulSoup sibling traversal should not fail for parsed tables
        return None


def normalize_row_match_value(value):
    """Normalize a cell value for row matching without changing actual diff output."""
    text = str(value).replace("\xa0", " ")
    return " ".join(text.split()).casefold()


def should_ignore_table_diff_field(column_heading, row_label=None):
    if column_heading == "Version ID":
        return True
    if row_label and str(row_label).strip() == "Program Version and Build":
        return True
    return False


def row_cells_for_match(trow):
    return [normalize_row_match_value(tcol.get_text(" ", strip=True)) for tcol in trow("td")]


def row_order_changed(original_rows, reordered_rows):
    return any(original_row is not reordered_row for original_row, reordered_row in zip(original_rows, reordered_rows))


def reorder_rows_to_match(base_keys, search_keys, search_rows):
    rows_by_key = defaultdict(deque)
    for key, row in zip(search_keys, search_rows):
        rows_by_key[tuple(key)].append(row)

    reordered_rows = []
    for key in base_keys:
        normalized_key = tuple(key)
        if not rows_by_key[normalized_key]:
            return search_rows
        reordered_rows.append(rows_by_key[normalized_key].popleft())
    return reordered_rows


def match_search_rows_to_base_rows_with_status(base_rows, search_rows):
    """
    Reorder search_rows to match base_rows when row order is not semantically meaningful.

    First, try a whole-row match using normalized values so case-only formatting changes do
    not block reorder detection. If rows have real diffs, fall back to the shortest unique
    leading-column key that exists in both tables. This lets us align rows like coil sizing
    outputs where the stable row identifier is early in the row, but values later in the row
    may legitimately differ.
    """
    if not base_rows or not search_rows:
        return search_rows, False

    base_keys = [row_cells_for_match(trow) for trow in base_rows]
    search_keys = [row_cells_for_match(trow) for trow in search_rows]

    if base_keys == search_keys:
        return search_rows, False

    if Counter(map(tuple, base_keys)) == Counter(map(tuple, search_keys)):
        reordered_rows = reorder_rows_to_match(base_keys, search_keys, search_rows)
        return reordered_rows, row_order_changed(search_rows, reordered_rows)

    max_prefix_len = min(
        min((len(key) for key in base_keys), default=0),
        min((len(key) for key in search_keys), default=0),
    )

    for prefix_len in range(1, max_prefix_len + 1):
        base_prefixes = [tuple(key[:prefix_len]) for key in base_keys]
        if len(set(base_prefixes)) != len(base_prefixes):
            continue

        search_prefixes = [tuple(key[:prefix_len]) for key in search_keys]
        if Counter(base_prefixes) != Counter(search_prefixes):
            continue

        reordered_rows = reorder_rows_to_match(base_prefixes, search_prefixes, search_rows)
        return reordered_rows, row_order_changed(search_rows, reordered_rows)

    return search_rows, False


def match_search_rows_to_base_rows(base_rows, search_rows):
    reordered_rows, _ = match_search_rows_to_base_rows_with_status(base_rows, search_rows)
    return reordered_rows


def _cell_heading(cell: Tag) -> str:
    return cell.contents[0] if cell.contents else FIELD_DUMMY


def _cell_contents(cell: Tag) -> str:
    return cell.contents[0] if cell.contents else ""


def hdict2soup(soup, heading, num, hdict, tdict, horder):
    """Create soup table (including anchor and heading) from header dictionary and error dictionary."""
    soup.body.append(Tag(soup, name="a", attrs={"name": f"tablehead{num}"}))

    htag = Tag(soup, name="b")
    htag.append(heading)
    soup.body.append(htag)

    tabletag = Tag(soup, name="table", attrs={"border": "1"})
    soup.body.append(tabletag)

    heading_row = Tag(soup, name="tr")
    tabletag.append(heading_row)
    for heading_name in horder:
        _append_text_cell(soup, heading_row, "th", "" if heading_name == FIELD_DUMMY else heading_name)

    absolute_row = Tag(soup, name="tr")
    tabletag.append(absolute_row)
    for heading_name in horder:
        text = str(tdict[heading_name][0]) if heading_name in tdict else "Absolute threshold"
        _append_text_cell(soup, absolute_row, "td", text)

    relative_row = Tag(soup, name="tr")
    tabletag.append(relative_row)
    for heading_name in horder:
        text = str(tdict[heading_name][1]) if heading_name in tdict else "Relative threshold"
        _append_text_cell(soup, relative_row, "td", text)

    for row_index in range(0, len(hdict[horder[0]])):
        row = Tag(soup, name="tr")
        tabletag.append(row)
        for heading_name in horder:
            if heading_name not in hdict:
                _append_text_cell(soup, row, "td", "ColumnHeadingDifference", DIFF_BIG)
                continue

            value = hdict[heading_name][row_index]
            if heading_name == FIELD_SUBCATEGORY:
                _append_text_cell(soup, row, "td", value)
            elif heading_name == FIELD_DUMMY and isinstance(value, tuple) and len(value) == 2:
                diff, which = value
                _append_text_cell(soup, row, "td", diff, which)
            elif heading_name == FIELD_DUMMY:
                _append_text_cell(soup, row, "td", value)
            else:
                diff, which = value
                _append_text_cell(soup, row, "td", diff, which)


def table2hdict_horder(table, table_a=None):
    """Convert an HTML table to a heading dictionary and ordered heading list."""
    hdict: dict[str, list] = {}
    horder = []
    rows = table("tr")
    heading_cells = rows[0]("td")

    for cell in heading_cells:
        heading = _cell_heading(cell)
        hdict[heading] = []
        horder.append(heading)

    search_rows = rows[1:]
    reordered = False
    if table_a:
        search_rows, reordered = match_search_rows_to_base_rows_with_status(table_a("tr")[1:], search_rows)

    for row in search_rows:
        for heading_cell, data_cell in zip(heading_cells, row("td")):
            hdict[_cell_heading(heading_cell)].append(_cell_contents(data_cell))

    return hdict, horder, reordered


def _make_error_table(err_soup: BeautifulSoup) -> Tag:
    tabletag = Tag(err_soup, name="table", attrs={"border": "1"})
    err_soup.body.append(tabletag)

    row = Tag(err_soup, name="tr")
    tabletag.append(row)
    for title in [
        "Table",
        "Abs file",
        "Rel file",
        "Big diffs",
        "Small diffs",
        "Equals",
        "String diffs",
        "Size diffs",
        "Reordered",
    ]:
        _append_text_cell(err_soup, row, "th", title)
    return tabletag


def make_err_table_row(err_soup, tabletag, uheading, count_of_tables, abs_diff_file, rel_diff_file,
                       small_diff, big_diff, equal, string_diff, size_error, not_in_1, not_in_2, reordered):
    row = Tag(err_soup, name="tr")
    tabletag.append(row)

    _append_text_cell(err_soup, row, "td", uheading)
    abs_cell = _append_text_cell(err_soup, row, "td")
    rel_cell = _append_text_cell(err_soup, row, "td")

    if small_diff > 0 or big_diff > 0 or string_diff > 0:
        abs_link = Tag(
            err_soup,
            name="a",
            attrs={"href": f"{os.path.basename(abs_diff_file)}#tablehead{count_of_tables}"},
        )
        abs_link.append("abs file")
        abs_cell.append(abs_link)

        rel_link = Tag(
            err_soup,
            name="a",
            attrs={"href": f"{os.path.basename(rel_diff_file)}#tablehead{count_of_tables}"},
        )
        rel_link.append("rel file")
        rel_cell.append(rel_link)

    _append_text_cell(err_soup, row, "td", big_diff, DIFF_BIG if big_diff > 0 else None)
    _append_text_cell(err_soup, row, "td", small_diff, DIFF_SMALL if small_diff > 0 else None)
    _append_text_cell(err_soup, row, "td", equal)
    _append_text_cell(err_soup, row, "td", string_diff, DIFF_STRING if string_diff > 0 else None)

    size_text = (
        "size mismatch" if size_error > 0 else "not in 1" if not_in_1 > 0 else "not in 2" if not_in_2 > 0 else ""
    )
    size_class = TABLE_SIZE_ERROR if size_error > 0 or not_in_1 > 0 or not_in_2 > 0 else None
    _append_text_cell(err_soup, row, "td", size_text, size_class)
    _append_text_cell(err_soup, row, "td", "yes" if reordered else "", DIFF_REORDERED if reordered else None)


def _add_error_row(
    err_soup: BeautifulSoup,
    tabletag: Tag,
    heading: str,
    table_count: int,
    abs_diff_file: str,
    rel_diff_file: str,
    counts: DiffCounts,
    reordered: bool,
) -> None:
    make_err_table_row(
        err_soup,
        tabletag,
        heading,
        table_count,
        abs_diff_file,
        rel_diff_file,
        counts.small,
        counts.big,
        counts.equal,
        counts.string,
        counts.size_error,
        counts.not_in_1,
        counts.not_in_2,
        reordered,
    )


def _headings_changed(horder1: list[str], horder2: list[str]) -> bool:
    return any(heading not in horder2 for heading in horder1) or any(heading not in horder1 for heading in horder2)


def _compare_dummy_column(hdict1, hdict2, horder2, counts: DiffCounts) -> list[DisplayValue]:
    if FIELD_DUMMY not in horder2:
        return hdict1[FIELD_DUMMY]

    values = []
    for x, y in zip(hdict1[FIELD_DUMMY], hdict2[FIELD_DUMMY]):
        diff_result = thresh_abs_rel_diff(0, 0, x, y)
        if diff_result[2] == DIFF_STRING:
            values.append((diff_result[0], diff_result[2]))
            counts.string += 1
        else:
            values.append(x)
    return values


def _compare_data_column(h, hdict1, hdict2, horder2, table1, thresh_dict: ThreshDict, counts: DiffCounts, thresholds):
    if h not in horder2:
        values = [[0, 0, DIFF_BIG]] * (len(table1("tr")) - 1)
        for diff_result in values:
            counts.add_diff_type(diff_result[2])
        return values

    abs_thresh, rel_thresh = thresh_dict.lookup(h)
    thresholds[h] = (abs_thresh, rel_thresh)
    row_labels = hdict1.get(FIELD_DUMMY, [])
    values = []
    for row_index, (x, y) in enumerate(zip(hdict1[h], hdict2[h])):
        row_label = row_labels[row_index] if row_index < len(row_labels) else None
        if should_ignore_table_diff_field(h, row_label):
            values.append((0, 0, DIFF_EQUAL))
        else:
            values.append(thresh_abs_rel_diff(abs_thresh, rel_thresh, x, y))

    for diff_result in values:
        if should_ignore_table_diff_field(h):
            counts.equal += 1
        else:
            counts.add_diff_type(diff_result[2])
    return values


def _compare_tables(table1, table2, table_reordered: bool, thresh_dict: ThreshDict) -> TableComparison:
    hdict1, horder1, _ = table2hdict_horder(table1)
    hdict2, horder2, rows_reordered = table2hdict_horder(table2, table1)
    table_reordered = table_reordered or rows_reordered

    counts = DiffCounts(reordered=1 if table_reordered else 0)
    if _headings_changed(horder1, horder2):
        counts.size_error += 1
        counts.string += 1
        counts.big += 1

    diff_dict = {}
    thresholds = {}
    for heading in horder1:
        if heading == FIELD_DUMMY:
            diff_dict[heading] = _compare_dummy_column(hdict1, hdict2, horder2, counts)
        else:
            diff_dict[heading] = _compare_data_column(
                heading,
                hdict1,
                hdict2,
                horder2,
                table1,
                thresh_dict,
                counts,
                thresholds,
            )

    return TableComparison(counts, diff_dict, horder1, horder2, thresholds, table_reordered)


def _diff_output_dict(comparison: TableComparison, horder2: list[str], index: int) -> dict[str, list[DisplayValue]]:
    output = {}
    for heading in comparison.horder:
        if heading not in horder2 and heading != FIELD_DUMMY:
            continue
        values = comparison.diff_dict[heading]
        if heading in (FIELD_DUMMY, FIELD_SUBCATEGORY):
            output[heading] = values
        else:
            output[heading] = [(diff[index], diff[2]) for diff in values]
    return output


def _write_summary(summary_file: str, case_name: str, table_count: int, counts: DiffCounts) -> None:
    if not os.path.exists(summary_file):
        with open(summary_file, "w") as summarize:
            summarize.write(SUMMARY_HEADER)
    with open(summary_file, "a") as summarize:
        summarize.write(
            f"{case_name},{table_count},{counts.big},{counts.small},{counts.equal},{counts.string},"
            f"{counts.size_error},{counts.not_in_1},{counts.not_in_2},{counts.reordered}\n"
        )


def _matching_table_from_file_2(tables2, uheadings2, heading, uheading_positions2, table1_index):
    table2_order_index = uheading_positions2[heading].popleft()

    # Preserve the historical duplicate-heading behavior: duplicate table names
    # are compared against the first matching table, while the consumed position
    # is used only to detect table reordering.
    table2_index = uheadings2.index(heading)
    return tables2[table2_index], table2_order_index != table1_index


def table_diff(
        thresh_dict: ThreshDict, input_file_1: str, input_file_2: str, abs_diff_file: str,
        rel_diff_file: str, err_file: str, summary_file: str
):
    """
    Compare two xxxTable.html files returning:

    (
        <message>, <#tables>, <#big_diff>,
        <#small_diff>, <#equals>, <#string_diff>,
        <#size_diff>, <#not_in_file1>, <#not_in_file2>, <#reordered_tables>
    )
    """
    file_1 = Path(input_file_1)
    file_2 = Path(input_file_2)
    case_name = file_1.parent.name

    if not file_1.exists():
        return _empty_result(f"unable to open file <{input_file_1}>")
    if not file_2.exists():
        return _empty_result(f"unable to open file <{input_file_2}>")

    page_title = f"{file_1.name} vs {file_2.name}"
    err_soup = _new_soup(page_title + " -- summary")
    abs_diff_soup = _new_soup(page_title + " -- absolute differences")
    rel_diff_soup = _new_soup(page_title + " -- relative differences")
    tabletag = _make_error_table(err_soup)

    soup1 = BeautifulSoup(_read_html(file_1), features="html.parser")
    soup2 = BeautifulSoup(_read_html(file_2), features="html.parser")
    tables1 = soup1("table")
    tables2 = soup2("table")
    uheadings1 = [get_table_unique_heading(table) for table in tables1]
    uheadings2 = [get_table_unique_heading(table) for table in tables2]

    if any(heading is None for heading in uheadings1):
        return _empty_result(f"malformed comment/table structure in <{input_file_1}>")
    if any(heading is None for heading in uheadings2):
        return _empty_result(f"malformed comment/table structure in <{input_file_2}>")

    matching_headings = set(uheadings1).intersection(set(uheadings2))
    uheading_positions2 = defaultdict(deque)
    for index, heading in enumerate(uheadings2):
        uheading_positions2[heading].append(index)

    table_count = 0
    changed_table_count = 0
    total_counts = DiffCounts()

    for table1_index, uheading1 in enumerate(uheadings1):
        table_count += 1

        if any(skip_key in uheading1 for skip_key in SKIPPABLE_TABLE_KEYS):
            continue

        if uheading1 not in matching_headings:
            counts = DiffCounts(big=1, not_in_2=1)
            total_counts.add(counts)
            _add_error_row(err_soup, tabletag, uheading1, table_count, abs_diff_file, rel_diff_file, counts, False)
            continue

        table1 = tables1[table1_index]
        table2, table_reordered = _matching_table_from_file_2(
            tables2, uheadings2, uheading1, uheading_positions2, table1_index
        )

        if len(table1("tr")) != len(table2("tr")) or len(table1("td")) != len(table2("td")):
            counts = DiffCounts(big=1, size_error=1, reordered=1 if table_reordered else 0)
            total_counts.add(counts)
            _add_error_row(
                err_soup, tabletag, uheading1, table_count, abs_diff_file, rel_diff_file, counts, table_reordered
            )
            continue

        comparison = _compare_tables(table1, table2, table_reordered, thresh_dict)
        total_counts.add(comparison.counts)
        _add_error_row(
            err_soup,
            tabletag,
            uheading1,
            table_count,
            abs_diff_file,
            rel_diff_file,
            comparison.counts,
            comparison.reordered,
        )

        if not comparison.counts.has_reportable_diff():
            continue

        hdict2soup(
            abs_diff_soup,
            uheading1,
            table_count,
            _diff_output_dict(comparison, comparison.horder2, 0).copy(),
            comparison.thresholds,
            comparison.horder,
        )
        hdict2soup(
            rel_diff_soup,
            uheading1,
            table_count,
            _diff_output_dict(comparison, comparison.horder2, 1).copy(),
            comparison.thresholds,
            comparison.horder,
        )
        changed_table_count += 1

    for uheading2 in uheadings2:
        if uheading2 not in matching_headings:
            table_count += 1
            counts = DiffCounts(not_in_1=1)
            total_counts.add(counts)
            _add_error_row(err_soup, tabletag, uheading2, table_count, abs_diff_file, rel_diff_file, counts, False)

    _write_html(err_file, err_soup)
    if changed_table_count > 0:
        _write_html(abs_diff_file, abs_diff_soup)
        _write_html(rel_diff_file, rel_diff_soup)

    if summary_file:
        _write_summary(summary_file, case_name, table_count, total_counts)

    return _result_tuple("", table_count, total_counts)


def main(argv=None) -> int:  # pragma: no cover
    if argv is None:
        argv = sys.argv
    try:
        opts, args = getopt.getopt(argv[1:], "ho:v", ["help", "output="])
    except getopt.error as msg:
        print(sys.argv[0].split("/")[-1] + ": " + str(msg) + "\n\t for help use --help")
        return -1

    [input_file_1, input_file_2, abs_diff_file, rel_diff_file, err_file, summary_file] = args
    thresh_dict = ThreshDict(os.path.join(script_dir, "math_diff.config"))
    table_diff(thresh_dict, input_file_1, input_file_2, abs_diff_file, rel_diff_file, err_file, summary_file)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
