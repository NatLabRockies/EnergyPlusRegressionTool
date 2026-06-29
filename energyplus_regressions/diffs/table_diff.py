#!/usr/bin/env python

"""Takes two E+ html output files and compares them
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
# VERSION: 1.3

__author__ = "Santosh Philip (santosh_philip at yahoo dot com) and Amir Roth (amir dot roth at ee dot doe dot gov)"
__version__ = "1.4"
__copyright__ = "Copyright (c) 2009 Santosh Philip and Amir Roth 2013"
__license__ = "GNU General Public License Version 3"

from pathlib import Path
from collections import Counter, defaultdict, deque
import sys
import getopt
import os.path

from bs4 import BeautifulSoup, NavigableString, Tag
from energyplus_regressions.diffs.thresh_dict import ThreshDict

help_message = __doc__

this_file = Path(__file__).resolve()
script_dir = this_file.parent

title_css = """<!DOCTYPE html PUBLIC "-
//W3C//DTD XHTML 1.0 Strict//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"><html xmlns="http://www.w3.org/1999/xhtml">
<head><title>%s</title>  <style type="text/css"> %s </style>
<meta name="generator" content="BBEdit 8.2" /></head>
<body></body></html>
"""

title_html = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>%s</title>
    <meta name="generator" content="BBEdit 8.2" />
</head>
<body>

</body>
</html>
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


def thresh_abs_rel_diff(abs_thresh: float, rel_thresh: float, x: str, y: str) -> tuple[float | str, float | str, str]:
    if x == y:
        return 0, 0, 'equal'
    try:
        fx = float(x)
        fy = float(y)
        if fx == fy:
            return 0, 0, 'equal'
        abs_diff = abs(fx - fy)
        rel_diff = abs((fx - fy) / fx) if abs(fx) > abs(fy) else abs((fy - fx) / fy)
        diff = 'equal'
        if abs_diff > abs_thresh and rel_diff > rel_thresh:
            diff = 'big'
        elif (0 < abs_diff <= abs_thresh) or (0 < rel_diff <= rel_thresh):
            diff = 'small'
        return abs_diff, rel_diff, diff
    except ValueError:
        # if we couldn't get a float out of it, do a string comparison after trimming edge whitespace
        if x.strip() == y.strip():
            return 0, 0, 'equal'
        else:
            return f'{x} vs {y}', f'{x} vs {y}', 'stringdiff'


def prev_sib(entity):
    """get soup.previous_sibling ignoring stripping out all blank spaces"""
    prevs = entity
    i = 0
    while i == 0:
        prevs = prevs.previous_sibling
        if isinstance(prevs, NavigableString):
            utxt = prevs.strip()
            if utxt == '':
                continue
        return prevs


def get_table_unique_heading(table):
    """return table unique name which should be in comment immediately before table"""
    # noinspection PyBroadException
    try:
        val = prev_sib(table)
        if val:
            return '%s' % val
        else:
            return None
    except:  # pragma: no cover - AFAIK the prev_sib will always return _something_, including None, but I can't be sure
        return None


def normalize_row_match_value(value):
    """Normalize a cell value for row matching without changing actual diff output."""
    text = str(value).replace('\xa0', ' ')
    return ' '.join(text.split()).casefold()


def should_ignore_table_diff_field(column_heading, row_label=None):
    if column_heading == 'Version ID':
        return True
    if row_label and str(row_label).strip() == 'Program Version and Build':
        return True
    return False


def row_cells_for_match(trow):
    return [normalize_row_match_value(tcol.get_text(' ', strip=True)) for tcol in trow('td')]


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


def hdict2soup(soup, heading, num, hdict, tdict, horder):
    """Create soup table (including anchor and heading) from header dictionary and error dictionary"""
    # Append table anchor
    atag = Tag(soup, name='a', attrs={'name': '%s%s' % ('tablehead', num,)})
    soup.body.append(atag)

    # Append table heading
    htag = Tag(soup, name='b')
    htag.append(heading)
    soup.body.append(htag)

    # Append table
    tabletag = Tag(soup, name='table', attrs={'border': '1'})
    soup.body.append(tabletag)

    # Append column headings
    trtag = Tag(soup, name='tr')
    tabletag.append(trtag)
    for h in horder:
        tdtag = Tag(soup, name='th')
        if h != 'DummyPlaceholder':
            tdtag.append(str(h))
        else:
            tdtag.append('')
        trtag.append(tdtag)

    # Append column thresholds
    trtag = Tag(soup, name='tr')
    tabletag.append(trtag)
    for h in horder:
        tdtag = Tag(soup, name='td')
        trtag.append(tdtag)
        if h in tdict:
            (abs_thresh, rel_thresh) = tdict[h]
            tdtag.append(str(abs_thresh))
        else:
            tdtag.append('Absolute threshold')

    trtag = Tag(soup, name='tr')
    tabletag.append(trtag)
    for h in horder:
        tdtag = Tag(soup, name='td')
        trtag.append(tdtag)
        if h in tdict:
            (abs_thresh, rel_thresh) = tdict[h]
            tdtag.append(str(rel_thresh))
        else:
            tdtag.append('Relative threshold')

    # Append table rows
    for i in range(0, len(hdict[horder[0]])):
        trtag = Tag(soup, name='tr')
        tabletag.append(trtag)
        for h in horder:
            if h not in hdict:
                tdtag = Tag(soup, name='td', attrs={"class": "big"})
                tdtag.append('ColumnHeadingDifference')
            elif h == 'Subcategory':
                # Some tables such as the Source Energy End Use Components
                # have a blank row full of `<td>&nbsp;</td>` which won't be
                # decoded nicely
                tdtag = Tag(soup, name='td')
                val = hdict[h][i]
                try:
                    tdtag.append(str(val))
                except Exception:  # pragma: no cover
                    val = val.encode('ascii', 'ignore').decode('ascii')
                    tdtag.append(str(val))
            elif h == 'DummyPlaceholder':
                val = hdict[h][i]
                if isinstance(val, tuple) and len(val) == 2:
                    diff, which = val
                    tdtag = Tag(soup, name='td', attrs={'class': which})
                    try:
                        tdtag.append(str(diff))
                    except Exception:  # pragma: no cover
                        diff = diff.encode('ascii', 'ignore').decode('ascii')
                        tdtag.append(str(diff))
                else:
                    tdtag = Tag(soup, name='td')
                    try:
                        tdtag.append(str(val))
                    except Exception:  # pragma: no cover
                        val = val.encode('ascii', 'ignore').decode('ascii')
                        tdtag.append(str(val))
            else:
                (diff, which) = hdict[h][i]
                tdtag = Tag(soup, name='td', attrs={'class': which})
                try:
                    tdtag.append(str(diff))
                except Exception:  # pragma: no cover
                    diff = diff.encode('ascii', 'ignore').decode('ascii')
                    tdtag.append(str(diff))
            trtag.append(tdtag)


# Convert html table to heading dictionary (and header list) in single step
def table2hdict_horder(table, table_a=None):
    # If table_a_hdict is passed in, we can try to match the row order to avoid diffs just due to row order
    hdict = {}
    horder = []
    trows = table('tr')

    # Create dictionary headings
    for htd in trows[0]('td'):
        try:
            hcontents = htd.contents[0]
        except IndexError:
            hcontents = 'DummyPlaceholder'

        hdict[hcontents] = []
        horder.append(hcontents)

    # Assume we are going to just loop over the rows and compare the data
    search_rows = trows[1:]

    # But we can handle it specially if we passed in table_a and the rows are just reordered.
    # Prefer whole-row matching first, but if a row has actual value diffs we can still align it
    # by the shortest unique leading-column key that exists in both tables.
    reordered = False
    if table_a:
        trows_a = table_a('tr')
        search_rows, reordered = match_search_rows_to_base_rows_with_status(trows_a[1:], search_rows)

    # whether it was reordered or just using the literal order, build out the hdict instance to pass back
    for trow in search_rows:
        for htd, td in zip(trows[0]('td'), trow('td')):
            try:
                hcontents = htd.contents[0]
            except IndexError:
                hcontents = 'DummyPlaceholder'

            try:
                contents = td.contents[0]
            except IndexError:
                contents = ''

            hdict[hcontents].append(contents)

    return hdict, horder, reordered


def make_err_table_row(err_soup, tabletag, uheading, count_of_tables, abs_diff_file, rel_diff_file,
                       small_diff, big_diff, equal, string_diff, size_error, not_in_1, not_in_2, reordered):
    # Create entry in error table
    trtag = Tag(err_soup, name='tr')
    tabletag.append(trtag)

    tdtag_name = Tag(err_soup, name='td')
    trtag.append(tdtag_name)
    tdtag_name.append(uheading)

    tdtag_abs_link = Tag(err_soup, name='td')
    trtag.append(tdtag_abs_link)

    tdtag_rel_link = Tag(err_soup, name='td')
    trtag.append(tdtag_rel_link)

    if small_diff > 0 or big_diff > 0 or string_diff > 0:
        file_name = os.path.basename(abs_diff_file)
        atag = Tag(err_soup, name='a', attrs={'href': '%s#tablehead%s' % (file_name, count_of_tables)})
        atag.append('abs file')
        tdtag_abs_link.append(atag)

        file_name = os.path.basename(rel_diff_file)
        atag = Tag(err_soup, name='a', attrs={'href': '%s#tablehead%s' % (file_name, count_of_tables)})
        atag.append('rel file')
        tdtag_rel_link.append(atag)

    tdtag_big_diff = Tag(err_soup, name='td', attrs={'class': 'big'} if big_diff > 0 else None)
    trtag.append(tdtag_big_diff)
    tdtag_big_diff.append(str(big_diff))

    tdtag_small_diff = Tag(err_soup, name='td', attrs={'class': 'small'} if small_diff > 0 else None)
    trtag.append(tdtag_small_diff)
    tdtag_small_diff.append(str(small_diff))

    tdtag_equal = Tag(err_soup, name='td')
    trtag.append(tdtag_equal)
    tdtag_equal.append(str(equal))

    tdtag_string_diff = Tag(err_soup, name='td', attrs={'class': 'stringdiff'} if string_diff > 0 else None)
    trtag.append(tdtag_string_diff)
    tdtag_string_diff.append(str(string_diff))

    tdtag_table_size_error = Tag(
        err_soup,
        name='td',
        attrs={'class': 'table_size_error'} if size_error > 0 or not_in_1 > 0 or not_in_2 > 0 else None
    )
    trtag.append(tdtag_table_size_error)
    tdtag_table_size_error.append(
        'size mismatch' if size_error > 0 else 'not in 1' if not_in_1 > 0 else 'not in 2' if not_in_2 > 0 else '')

    tdtag_reordered = Tag(err_soup, name='td', attrs={'class': 'reordered'} if reordered else None)
    trtag.append(tdtag_reordered)
    tdtag_reordered.append('yes' if reordered else '')


def table_diff(
        thresh_dict: ThreshDict, input_file_1: str, input_file_2: str, abs_diff_file: str,
        rel_diff_file: str, err_file: str, summary_file: str
):
    """
    Compares two xxxTable.html files returning
    (
        <message>, <#tables>, <#big_diff>,
        <#small_diff>, <#equals>, <#string_diff>,
        <#size_diff>, <#not_in_file1>, <#not_in_file2>, <#reordered_tables>
    )
    """
    file_1 = Path(input_file_1)
    file_2 = Path(input_file_2)

    case_name = file_1.parent.name

    # Test for existence of input files
    if not file_1.exists():
        return 'unable to open file <%s>' % input_file_1, 0, 0, 0, 0, 0, 0, 0, 0, 0
    if not file_2.exists():
        return 'unable to open file <%s>' % input_file_2, 0, 0, 0, 0, 0, 0, 0, 0, 0

    with open(file_1, 'rb') as f_1:
        txt1 = f_1.read().decode('utf-8', errors='ignore')
    with open(file_2, 'rb') as f_2:
        txt2 = f_2.read().decode('utf-8', errors='ignore')

    page_title = f'{file_1.name} vs {file_2.name}'

    # Error soup
    err_soup = BeautifulSoup(title_css % (page_title + ' -- summary', the_css,), features='html.parser')

    # Abs diff soup
    abs_diff_soup = BeautifulSoup(title_css % (page_title + ' -- absolute differences', the_css,),
                                  features='html.parser')

    # Rel diff soup
    rel_diff_soup = BeautifulSoup(title_css % (page_title + ' -- relative differences', the_css,),
                                  features='html.parser')

    # Make error table
    tabletag = Tag(err_soup, name='table', attrs={'border': '1'})
    err_soup.body.append(tabletag)

    # Make error table headings
    trtag = Tag(err_soup, name='tr')
    tabletag.append(trtag)
    for title in [
        'Table', 'Abs file', 'Rel file', 'Big diffs', 'Small diffs', 'Equals', 'String diffs', 'Size diffs',
        'Reordered'
    ]:
        thtag = Tag(err_soup, name='th')
        trtag.append(thtag)
        thtag.append(title)

    # Soup up the HTML input files
    soup2 = BeautifulSoup(txt2, features='html.parser')
    soup1 = BeautifulSoup(txt1, features='html.parser')

    tables1 = soup1('table')
    tables2 = soup2('table')

    uheadings1 = []
    uheadings2 = []
    for table in tables1:
        uheadings1.append(get_table_unique_heading(table))
    for table in tables2:
        uheadings2.append(get_table_unique_heading(table))

    if any([x is None for x in uheadings1]):
        return 'malformed comment/table structure in <%s>' % input_file_1, 0, 0, 0, 0, 0, 0, 0, 0, 0
    if any([x is None for x in uheadings2]):
        return 'malformed comment/table structure in <%s>' % input_file_2, 0, 0, 0, 0, 0, 0, 0, 0, 0

    uhset1 = set(uheadings1)
    uhset2 = set(uheadings2)
    uhset_match = set.intersection(uhset1, uhset2)
    uheading_positions2 = defaultdict(deque)
    for i2, uheading2 in enumerate(uheadings2):
        uheading_positions2[uheading2].append(i2)

    count_of_tables = 0
    count_of_tables_diff = 0

    count_of_small_diff = 0
    count_of_big_diff = 0
    count_of_equal = 0
    count_of_string_diff = 0
    count_of_size_error = 0
    count_of_not_in_1 = 0
    count_of_not_in_2 = 0
    count_of_reordered_tables = 0

    for i1 in range(0, len(list(uheadings1))):

        count_of_tables += 1

        table_small_diff = 0
        table_big_diff = 0
        table_equal = 0
        table_string_diff = 0
        table_size_error = 0
        table_not_in_1 = 0
        table_not_in_2 = 0
        table_reordered = False

        uheading1 = uheadings1[i1]

        # There are some (for now one) tables that we will want to skip entirely because they are not useful for
        # throwing regressions, add search keys to this list to skip them
        completely_skippable_table_keys = [
            'Object Count Summary_Entire Facility_Input Fields'
        ]
        if any([x in uheading1 for x in completely_skippable_table_keys]):
            continue

        # Table missing in second input file
        if uheading1 not in uhset_match:
            table_not_in_2 = 1
            count_of_not_in_2 += table_not_in_2
            table_big_diff = 1
            count_of_big_diff += table_big_diff
            make_err_table_row(err_soup, tabletag, uheading1, count_of_tables, abs_diff_file, rel_diff_file,
                               table_small_diff, table_big_diff, table_equal, table_string_diff, table_size_error,
                               table_not_in_1, table_not_in_2, table_reordered)
            continue

        table1 = tables1[i1]
        table2_index = uheadings2.index(uheading1)
        table2_order_index = uheading_positions2[uheading1].popleft()
        table2 = tables2[table2_index]
        table_reordered = table2_order_index != i1

        # Table size error
        if len(table1('tr')) != len(table2('tr')) or len(table1('td')) != len(table2('td')):
            table_size_error = 1
            count_of_size_error += table_size_error
            table_big_diff = 1
            count_of_big_diff += table_big_diff
            if table_reordered:
                count_of_reordered_tables += 1
            make_err_table_row(err_soup, tabletag, uheading1, count_of_tables, abs_diff_file, rel_diff_file,
                               table_small_diff, table_big_diff, table_equal, table_string_diff, table_size_error,
                               table_not_in_1, table_not_in_2, table_reordered)
            continue

        # always process the first table into a base hdict
        hdict1, horder1, _ = table2hdict_horder(table1)
        hdict2, horder2, rows_reordered = table2hdict_horder(table2, table1)
        table_reordered = table_reordered or rows_reordered
        if table_reordered:
            count_of_reordered_tables += 1

        # honestly, if the column headings have changed, this should be an indicator to all reviewers that this needs
        # up close investigation.  As such, we are going to trigger the following things:
        # 1) a table_size_error, because even though the sizes are the "same", the sizes have sort-of changed due to the
        #    missing column and added column in the second table
        # 2) a table_string_diff, because if the columns have changed, there must be at least one title different (yes
        #    even if it is duplicate, it is different because there is another one)
        # 3) a table_big_diff here, because something has definitely changed that needs attention
        # 4) each datum in each row that doesn't have a match should trigger a big diff as well later
        if any([h not in horder2 for h in horder1]) or any([h not in horder1 for h in horder2]):
            table_size_error += 1
            count_of_size_error += 1
            table_string_diff += 1
            count_of_string_diff += 1
            table_big_diff += 1
            count_of_big_diff += 1

        # Dictionaries of absolute and relative differences
        diff_dict = {}
        h_thresh_dict = {}

        for h in horder1:
            if h == 'DummyPlaceholder':
                if h not in horder2:
                    diff_dict[h] = hdict1[h]
                else:
                    diff_dict[h] = []
                    for x, y in zip(hdict1[h], hdict2[h]):
                        diff_result = thresh_abs_rel_diff(0, 0, x, y)
                        if diff_result[2] == 'stringdiff':
                            diff_dict[h].append((diff_result[0], diff_result[2]))
                            table_string_diff += 1
                            count_of_string_diff += 1
                        else:
                            diff_dict[h].append(x)
            else:
                if h not in horder2:
                    diff_dict[h] = [[0, 0, 'big']] * (len(table1('tr')) - 1)
                else:
                    (abs_thresh, rel_thresh) = thresh_dict.lookup(h)
                    h_thresh_dict[h] = (abs_thresh, rel_thresh)
                    diff_dict[h] = []
                    row_labels = hdict1.get('DummyPlaceholder', [])
                    for row_index, (x, y) in enumerate(zip(hdict1[h], hdict2[h])):
                        row_label = row_labels[row_index] if row_index < len(row_labels) else None
                        if should_ignore_table_diff_field(h, row_label):
                            diff_dict[h].append((0, 0, 'equal'))
                        else:
                            diff_dict[h].append(thresh_abs_rel_diff(abs_thresh, rel_thresh, x, y))

                # Statistics local to this table
                for diff_result in diff_dict[h]:
                    diff_type = diff_result[2]
                    if should_ignore_table_diff_field(h):
                        table_equal += 1
                        count_of_equal += 1
                    elif diff_type == 'small':
                        table_small_diff += 1
                        count_of_small_diff += 1
                    elif diff_type == 'big':
                        table_big_diff += 1
                        count_of_big_diff += 1
                    elif diff_type == 'equal':
                        table_equal += 1
                        count_of_equal += 1
                    if diff_type == 'stringdiff':
                        table_string_diff += 1
                        count_of_string_diff += 1

        make_err_table_row(err_soup, tabletag, uheading1, count_of_tables, abs_diff_file, rel_diff_file,
                           table_small_diff, table_big_diff, table_equal, table_string_diff, table_size_error,
                           table_not_in_1, table_not_in_2, table_reordered)

        # If there were no differences, we are done
        if (table_small_diff == 0) and (table_big_diff == 0) and (table_string_diff == 0):
            continue

        # Add difference tables to absolute and relative difference soups
        abs_diff_dict = {}
        for h in horder1:
            if h not in horder2:
                continue
            abs_diff_dict[h] = diff_dict[h] if (h == 'DummyPlaceholder' or h == 'Subcategory') else [
                (x_y_z[0], x_y_z[2]) for x_y_z in diff_dict[h]]
        hdict2soup(abs_diff_soup, uheading1, count_of_tables, abs_diff_dict.copy(), h_thresh_dict, horder1)

        rel_diff_dict = {}
        for h in horder1:
            if h not in horder2:
                continue
            rel_diff_dict[h] = diff_dict[h] if (h == 'DummyPlaceholder' or h == 'Subcategory') else [
                (x_y_z[1], x_y_z[2]) for x_y_z in diff_dict[h]]
        hdict2soup(rel_diff_soup, uheading1, count_of_tables, rel_diff_dict.copy(), h_thresh_dict, horder1)

        count_of_tables_diff += 1

    for uheading2 in uheadings2:
        if uheading2 not in uhset_match:
            count_of_tables += 1
            count_of_not_in_1 += 1
            make_err_table_row(err_soup, tabletag, uheading2, count_of_tables, abs_diff_file, rel_diff_file,
                               0, 0, 0, 0, 0, 1, 0, False)

    # Write error file
    err_txt = err_soup.prettify()
    with open(err_file, 'wb') as f_out:
        f_out.write(err_txt.encode('utf-8', errors='ignore'))

    # Only write absolute and relative diff files if any tables were actually different
    if count_of_tables_diff > 0:
        abs_diff_txt = abs_diff_soup.prettify()
        with open(abs_diff_file, 'wb') as f_abs:
            f_abs.write(abs_diff_txt.encode('utf-8', errors='ignore'))

        rel_diff_txt = rel_diff_soup.prettify()
        with open(rel_diff_file, 'wb') as f_rel:
            f_rel.write(rel_diff_txt.encode('utf-8', errors='ignore'))

    if summary_file:
        if not os.path.exists(summary_file):
            with open(summary_file, 'w') as summarize:
                summarize.write(
                    "Case,TableCount,BigDiffCount,SmallDiffCount,EqualCount,"
                    "StringDiffCount,SizeErrorCount,NotIn1Count,NotIn2Count,ReorderedTableCount\n"
                )
        with open(summary_file, 'a') as summarize:
            summarize.write("%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n" % (
                case_name, count_of_tables, count_of_big_diff, count_of_small_diff, count_of_equal,
                count_of_string_diff,
                count_of_size_error, count_of_not_in_1, count_of_not_in_2, count_of_reordered_tables))

    return ('', count_of_tables, count_of_big_diff, count_of_small_diff, count_of_equal, count_of_string_diff,
            count_of_size_error, count_of_not_in_1, count_of_not_in_2, count_of_reordered_tables)


def main(argv=None) -> int:  # pragma: no cover
    if argv is None:
        argv = sys.argv
    try:
        opts, args = getopt.getopt(argv[1:], "ho:v", ["help", "output="])
    except getopt.error as msg:
        print(sys.argv[0].split("/")[-1] + ": " + str(msg) + "\n\t for help use --help")
        return -1

    [input_file_1, input_file_2, abs_diff_file, rel_diff_file, err_file, summary_file] = args
    thresh_dict = ThreshDict(os.path.join(script_dir, 'math_diff.config'))
    table_diff(thresh_dict, input_file_1, input_file_2, abs_diff_file, rel_diff_file, err_file, summary_file)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
