#!/usr/bin/env python
# encoding: utf-8
"""
Takes two csv files and compares them
usage:
    python mathdiff <input1> <input2> <abs_diff_out> <rel_diff_out> <err_log> <summary_csv>

    input1 = first input csv file
    input2 = second input csv file
    abs_diff_out = csv output file of absolute cell-wise differences between input1 and input2
                   abs_diff_out[i,j] = abs(input1[i,j] - input2[i,j])
    rel_diff_out = csv output file of relative cell-wise differences between input1 and input2
                   rel_diff_out[i,j] = abs((input1[i,j] - input2[i,j])/input1[i,j])
    err_log  = output file containing error log which includes
               summary of absolute and relative differences in inputs
               summary of input1
               summary of input2
               absolute differences of summary of input1 and summary of input2
               relative differences of summary of input1 and summary of input2
    summary_csv = output file containing csv rows for each result, but no details

    configuration file math_diff.config customizes absolute and relative difference thresholds
    for different unit/aggregation pairs, for instance:
               C,* = 0.1, 0.005
    means that all in fields reported in C (degrees Celsius) will be compared with an absolute
    difference tolerance of 0.1 degree C and 0.005 (0.5%) relative difference tolerance.
"""

# Copyright (C) 2009, 2010 Santosh Philip and 2013 Amir Roth
# This file is part of mathdiff.
#
# mathdiff is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mathdiff is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with mathdiff.  If not, see <http://www.gnu.org/licenses/>.
# VERSION: 1.3


__author__ = "Santosh Philip (santosh_philip at yahoo dot com) and Amir Roth (amir dot roth at ee dot doe dot gov)"
__version__ = "1.4"
__copyright__ = "Copyright (c) 2009, 2010 Santosh Philip and 2013 Amir Roth"
__license__ = "GNU General Public License Version 3"

# the following are documented at the bottom of this file
# - how the program will respond when the headers of the two csv file do not match
# - how the program will respond when the time stamps do not match
# - documentation of data structure in the program

import filecmp
import getopt
import os
import sys

from energyplus_regressions.diffs import mycsv
from energyplus_regressions.diffs.thresh_dict import ThreshDict

help_message = __doc__

path = os.path.dirname(__file__)
script_dir = os.path.abspath(path)


class DuplicateHeaderException(Exception):
    """docstring for DuplicateHeaderException"""
    pass


def fill_matrix_holes(mat):
    """matrix may have blanks. Sometimes the tail end of some rows will not have elements.
    Make sure all rows have the same length as the first row.
    Also remove cells if the row is longer than the first row"""
    num_cols = len(mat[0])
    for i, row in enumerate(mat[1:]):
        more_cells = num_cols - len(row)
        if more_cells >= 0:
            mat[i + 1] = row + [''] * more_cells
        else:
            mat[i + 1] = mat[i + 1][:more_cells]
    return mat


def slicetime(mat):
    """return two matrices, one with only time and the other with the rest of the matrix"""
    return [row[0:1] for row in mat], [row[1:] for row in mat]


def matrix2hdict(mat):
    """from a csv matrix make a dict with column headers as keys. This dict is called 'header dictionary' or hdict"""
    this_dict = {}
    t_mat = mycsv.transpose2d(mat)
    for col in t_mat:
        if col[0] in this_dict:
            raise DuplicateHeaderException("There are two columns with the same header name " + str(col[0]))
            # TODO - DuplicateHeaderException - this has to go into the error file and mini file
        else:
            this_dict[col[0]] = col[1:]
    return this_dict


def hdict2matrix(order, this_dict):
    """convert the header dictionary (as created by matrix2hdict) to a csv matrix held in mat.
    'order' is the order of the headers in the matrix. (order is needed because keys in a dict have no sort order)"""
    mat = []
    for key in order:
        mat.append([key] + list(this_dict[key]))
    return mycsv.transpose2d(mat)


summary_labels = [
    'count', 'sum', 'max', 'min', 'average', 'time_of_max', 'time_of_min',
    'nz_count', 'nz_sum', 'nz_max', 'nz_min', 'nz_average', 'nz_time_of_max', 'nz_time_of_min']

error_labels = (
    'abs_thresh', 'max_abs_diff', 'rel_diff_of_max_abs_diff', 'time_of_max_abs_diff', 'count_of_small_abs_diff',
    'count_of_big_abs_diff',
    'rel_thresh', 'max_rel_diff', 'abs_diff_of_max_rel_diff', 'time_of_max_rel_diff', 'count_of_small_rel_diff',
    'count_of_big_rel_diff',
    'count_of_small_abs_rel_diff', 'count_of_big_abs_rel_diff')


def make_summary_dict(tdict, hdict):
    """generate the summary dict"""
    sdict = {}
    times = tdict[list(tdict.keys())[0]]
    for key in hdict.keys():
        sdict[key] = {}
    for key in hdict.keys():
        column_error = False
        column = hdict[key]
        for i, cell in enumerate(column):  # make all cells floats
            cell = str(cell)
            if cell.strip() == '':
                column[i] = 0
            else:
                try:
                    column[i] = float(cell)
                except ValueError:  # pragma: no cover - I don't know how to get here
                    column_error = True  # Now we can't do any summary calcs for this column
                    break  # get out of this inner loop
        if column_error:  # pragma: no cover - I don't know how to get here
            continue  # go to next step in this outer loop

        sdict[key]['count'] = len(column)
        sdict[key]['sum'] = sum(column)
        sdict[key]['max'] = max(column)
        sdict[key]['min'] = min(column)
        sdict[key]['average'] = sdict[key]['sum'] / sdict[key]['count']
        sdict[key]['time_of_max'] = times[column.index(sdict[key]['max'])]
        sdict[key]['time_of_min'] = times[column.index(sdict[key]['min'])]

        nz_items = [item for item in column if item != 0]
        if not nz_items:
            sdict[key]['nz_count'] = 0
            sdict[key]['nz_sum'] = 0.0
            sdict[key]['nz_max'] = 0.0
            sdict[key]['nz_min'] = 0.0
            sdict[key]['nz_average'] = 0.0
            sdict[key]['nz_time_of_max'] = 0.0
            sdict[key]['nz_time_of_min'] = 0.0
        else:
            sdict[key]['nz_count'] = len(nz_items)
            sdict[key]['nz_sum'] = max(nz_items)
            sdict[key]['nz_max'] = max(nz_items)
            sdict[key]['nz_min'] = min(nz_items)
            sdict[key]['nz_average'] = sdict[key]['nz_sum'] / sdict[key]['nz_count']
            sdict[key]['nz_time_of_max'] = times[column.index(sdict[key]['nz_max'])]
            sdict[key]['nz_time_of_min'] = times[column.index(sdict[key]['nz_min'])]

    sdict[list(tdict.keys())[0]] = [label + ':' for label in summary_labels]
    return sdict


def dict_of_dicts2dict_of_lists(dict_of_dicts, key_order, list_labels):
    dict_of_lists = {}
    for key in key_order:
        dict_of_lists[key] = []
        for ll in list_labels:
            try:
                dict_of_lists[key].append(dict_of_dicts[key][ll])
            except (KeyError, ValueError):
                print(f"Encountered a ValueError, trying to find key: {ll}, can be caused by malformed CSV numerics")
                raise
    return dict_of_lists


def abs_diff(x, y):
    if x == y:
        return 0
    # noinspection PyBroadException
    try:
        return abs(float(x) - float(y))
    #        return (float(x)-float(y))
    except Exception:
        return 9999  # 'exception'


def rel_diff(x, y):
    if x == y:
        return 0
    # noinspection PyBroadException
    try:
        return abs((float(x) - float(y)) / (float(x))) if (abs(float(x)) > 0) else 999
    #        return (float(x)-float(y))/(float(x)+.00001)
    except Exception:
        return 9999  # 'exception'


def info(line, logfile=None):
    if logfile:
        mycsv.writecsv([[line]], logfile, 'a')
    # print >> sys.stderr, line


def write_summary_csv(summary_csv, input_file_1, diff_type, num_records):
    if not summary_csv:
        return
    input_file_path_tokens = input_file_1.split(os.sep)
    if not os.path.isfile(summary_csv):
        with open(summary_csv, 'w') as f:
            f.write("CaseName,FileName,Status,#Records\n")
    with open(summary_csv, 'a') as f:
        f.write(
            "%s,%s,%s,%s records compared\n" % (
                input_file_path_tokens[-2], input_file_path_tokens[-1], diff_type, num_records
            )
        )


def exact_match_result(input_file_1, input_file_2, err_file, summary_csv):
    if not filecmp.cmp(input_file_1, input_file_2, shallow=False):
        return None
    try:
        mat = mycsv.getlist(input_file_1)
    except IndexError:
        return 'malformed or empty csv file: <%s>' % input_file_1, 0, 0, 0
    if len(mat) < 2:
        info('<%s> has no data' % input_file_1, err_file)
        return '<%s> has no data' % input_file_1, 0, 0, 0
    if isinstance(mat[0], list) and len(set(mat[0])) != len(mat[0]):
        for header in mat[0]:
            if mat[0].count(header) > 1:
                raise DuplicateHeaderException("There are two columns with the same header name " + str(header))
    num_records = len(mat) - 1
    write_summary_csv(summary_csv, input_file_1, 'All Equal', num_records)
    return 'All Equal', num_records, 0, 0


def math_diff(thresh_dict, input_file_1, input_file_2, abs_diff_file, rel_diff_file, err_file, summary_csv):
    # Test for existence of input files
    if not os.path.exists(input_file_1):
        info('unable to open file <%s>' % input_file_1, err_file)
        return 'unable to open file <%s>' % input_file_1, 0, 0, 0
    if not os.path.exists(input_file_2):
        info('unable to open file <%s>' % input_file_2, err_file)
        return 'unable to open file <%s>' % input_file_2, 0, 0, 0

    fast_result = exact_match_result(input_file_1, input_file_2, err_file, summary_csv)
    if fast_result:
        return fast_result

    # read data out of files
    try:
        mat1 = mycsv.getlist(input_file_1)
    except IndexError:
        return 'malformed or empty csv file: <%s>' % input_file_1, 0, 0, 0
    if len(mat1) < 2:
        info('<%s> has no data' % input_file_1, err_file)
        return '<%s> has no data' % input_file_1, 0, 0, 0
    try:
        mat2 = mycsv.getlist(input_file_2)
    except IndexError:
        return 'malformed or empty csv file: <%s>' % input_file_2, 0, 0, 0
    if len(mat2) < 2:
        info('<%s> has no data' % input_file_2, err_file)
        return '<%s> has no data' % input_file_2, 0, 0, 0

    # clean up the files
    matrix1 = fill_matrix_holes(mat1)
    matrix2 = fill_matrix_holes(mat2)

    # split out the time columns
    time1, mat1 = slicetime(matrix1)
    time2, mat2 = slicetime(matrix2)
    # Not going to compare two files with different time series
    if time1 != time2:
        info('Time series in <%s> and <%s> do not match' % (input_file_1, input_file_2), err_file)
        return 'Time series do not match', 0, 0, 0

    # Only going to compare fields that are found in both files
    h_set_1 = set(mat1[0])
    h_set_2 = set(mat2[0])
    h_set = h_set_1.intersection(h_set_2)
    if len(h_set) == 0:
        info('Input files <%s> and <%s> have no common fields' % (input_file_1, input_file_2), err_file)
        return 'No common fields', 0, 0, 0

    # Order will be order in which intersection fields appear in first file
    h_order = [h for h in mat1[0] if h in h_set]

    # Warn about fields that will not be compared
    h_set_s_diff = h_set_1.symmetric_difference(h_set_2)
    for h in h_set_s_diff:
        if h in h_set_1:
            mycsv.writecsv(
                [
                    [
                        'Not comparing field %s, which appears in input files <%s>, but not <%s>' % (
                            h, input_file_1, input_file_2
                        )
                    ]
                ],
                err_file,
                'a'
            )
        else:
            mycsv.writecsv(
                [
                    [
                        'Not comparing field %s, which appears in input files <%s>, but not <%s>' % (
                            h,
                            input_file_2,
                            input_file_1
                        )
                    ]
                ],
                err_file,
                'a'
            )

    # convert time matrix to dictionary (both time matrices should be identical here)
    t_dict = matrix2hdict(time1)
    t_key = list(t_dict.keys())[0]

    # convert data matrices to dictionaries
    hdict1 = matrix2hdict(mat1)
    hdict2 = matrix2hdict(mat2)

    # Dictionaries of absolute and relative differences
    abs_diffs = {}
    rel_diffs = {}
    for key in h_order:
        abs_diffs[key] = list(map(abs_diff, hdict1[key], hdict2[key]))
        rel_diffs[key] = list(map(rel_diff, hdict1[key], hdict2[key]))

    err_dict = {}
    for key in h_order:
        err_dict[key] = {}

        (abs_thresh, rel_thresh) = thresh_dict.lookup(key)

        max_abs_diff = max(abs_diffs[key])
        index_max_abs_diff = abs_diffs[key].index(max_abs_diff)
        err_dict[key]['abs_thresh'] = abs_thresh
        err_dict[key]['max_abs_diff'] = max_abs_diff
        err_dict[key]['rel_diff_of_max_abs_diff'] = rel_diffs[key][index_max_abs_diff]
        err_dict[key]['time_of_max_abs_diff'] = t_dict[t_key][index_max_abs_diff]
        err_dict[key]['count_of_small_abs_diff'] = sum(1 for x in abs_diffs[key] if 0.0 < x <= abs_thresh)
        err_dict[key]['count_of_big_abs_diff'] = sum(1 for x in abs_diffs[key] if x > abs_thresh)

        max_rel_diff = max(rel_diffs[key])
        index_max_rel_diff = rel_diffs[key].index(max_rel_diff)

        err_dict[key]['rel_thresh'] = rel_thresh
        err_dict[key]['max_rel_diff'] = max_rel_diff
        err_dict[key]['abs_diff_of_max_rel_diff'] = abs_diffs[key][index_max_rel_diff]
        err_dict[key]['time_of_max_rel_diff'] = t_dict[t_key][index_max_rel_diff]
        if rel_thresh > 0:
            err_dict[key]['count_of_small_rel_diff'] = sum(1 for x in rel_diffs[key] if 0.0 < x <= rel_thresh)
            err_dict[key]['count_of_big_rel_diff'] = sum(1 for x in rel_diffs[key] if x > rel_thresh)
        else:
            err_dict[key]['count_of_small_rel_diff'] = 0
            err_dict[key]['count_of_big_rel_diff'] = 0

        if rel_thresh > 0:
            err_dict[key]['count_of_small_abs_rel_diff'] = sum(
                1 for x, y in zip(abs_diffs[key], rel_diffs[key]) if 0 < x <= abs_thresh or 0 < y <= rel_thresh
            )
            err_dict[key]['count_of_big_abs_rel_diff'] = sum(
                1 for x, y in zip(abs_diffs[key], rel_diffs[key]) if x > abs_thresh and y > rel_thresh
            )
        else:
            err_dict[key]['count_of_small_abs_rel_diff'] = err_dict[key]['count_of_small_abs_diff']
            err_dict[key]['count_of_big_abs_rel_diff'] = err_dict[key]['count_of_big_abs_diff']

    num_small = sum(err_dict[key]['count_of_small_abs_rel_diff'] for key in h_order)
    num_big = sum(err_dict[key]['count_of_big_abs_rel_diff'] for key in h_order)

    diff_type = 'All Equal'
    if num_big > 0:
        diff_type = 'Big Diffs'
    elif num_small > 0:
        diff_type = 'Small Diffs'

    num_records = len(t_dict[t_key])

    # if it's the first pass, create the file with the header;
    # also the null-pointer-ish check allows skipping the summary_csv file if the filename is blank
    write_summary_csv(summary_csv, input_file_1, diff_type, num_records)

    # We are done
    if diff_type == 'All Equal':
        return diff_type, num_records, num_big, num_small

    # Which columns had diffs?
    dh_order = [h for h in h_order if
                err_dict[h]['count_of_small_abs_diff'] > 0 or err_dict[h]['count_of_big_abs_diff'] > 0 or err_dict[h][
                    'count_of_small_rel_diff'] > 0 or err_dict[h]['count_of_big_rel_diff'] > 0]

    # Find the largest overall absolute diff
    max_max_abs_diff = max(err_dict[key]['max_abs_diff'] for key in dh_order)
    key_of_max_max_abs_diff = [key for key in dh_order if err_dict[key]['max_abs_diff'] == max_max_abs_diff][0]
    rel_diff_of_max_max_abs_diff = err_dict[key_of_max_max_abs_diff]['rel_diff_of_max_abs_diff']
    time_of_max_max_abs_diff = err_dict[key_of_max_max_abs_diff]['time_of_max_abs_diff']

    # Find the largest overall relative diff
    max_max_rel_diff = max(err_dict[key]['max_rel_diff'] for key in dh_order)
    key_of_max_max_rel_diff = [key for key in dh_order if err_dict[key]['max_rel_diff'] == max_max_rel_diff][0]
    abs_diff_of_max_max_rel_diff = err_dict[key_of_max_max_rel_diff]['abs_diff_of_max_rel_diff']
    time_of_max_max_rel_diff = err_dict[key_of_max_max_rel_diff]['time_of_max_rel_diff']

    # put the time column back
    abs_diffs[t_key] = t_dict[t_key]
    rel_diffs[t_key] = t_dict[t_key]

    # Summarize the input files
    summary_dict1 = make_summary_dict(t_dict, hdict1)
    summary_dict2 = make_summary_dict(t_dict, hdict2)

    # Flatten summaries out to dictionaries of lists rather than dictionaries of dictionaries
    summary_dict12 = dict_of_dicts2dict_of_lists(summary_dict1, h_order, list(summary_labels))
    summary_dict12[t_key] = [sl + ':' for sl in list(summary_labels)]

    summary_dict22 = dict_of_dicts2dict_of_lists(summary_dict2, h_order, list(summary_labels))
    summary_dict22[t_key] = [sl + ':' for sl in list(summary_labels)]

    # Diff the flattened summaries
    abs_diff_summary_dict = {}
    rel_diff_summary_dict = {}
    for key in dh_order:
        abs_diff_summary_dict[key] = map(abs_diff, summary_dict12[key], summary_dict22[key])
        rel_diff_summary_dict[key] = map(rel_diff, summary_dict12[key], summary_dict22[key])

    # Prepend time key to header order list
    th_order = [t_key] + h_order
    tdh_order = [t_key] + dh_order

    # Convert the absolute and relative diff dictionaries to matrices and write them to files
    abs_diff_mat = hdict2matrix(tdh_order, abs_diffs)
    # print("Trying to write to %s " % abs_diff_file)
    mycsv.writecsv(abs_diff_mat, abs_diff_file)
    rel_diff_mat = hdict2matrix(tdh_order, rel_diffs)
    mycsv.writecsv(rel_diff_mat, rel_diff_file)

    # Write the error file header
    mycsv.writecsv(
        [
            [],
            [
                'Max absolute diff: %s, field: %s, time: %s, relative: %s' % (
                    str(max_max_abs_diff),
                    str(key_of_max_max_abs_diff),
                    str(time_of_max_max_abs_diff),
                    str(rel_diff_of_max_max_abs_diff))
            ]
        ], err_file, 'a'
    )
    mycsv.writecsv(
        [
            [],
            [
                'Max relative diff: %s, field: %s, time: %s, absolute: %s' % (
                    str(max_max_rel_diff),
                    str(key_of_max_max_rel_diff),
                    str(time_of_max_max_rel_diff),
                    str(abs_diff_of_max_max_rel_diff))
            ]
        ], err_file, 'a'
    )

    # Convert the error dictionary to a matrix and write to the error
    # file.  Need to convert it from a nested dictionary to a
    # dictionary of lists first.
    err_dict2 = dict_of_dicts2dict_of_lists(err_dict, h_order, list(error_labels))
    err_dict2[t_key] = [el + ':' for el in list(error_labels)]

    err_mat = hdict2matrix(tdh_order, err_dict2)
    mycsv.writecsv([[], []] + err_mat, err_file, 'a')

    # Convert the summaries to matrices and write them out to the error file
    summary_mat1 = hdict2matrix(th_order, summary_dict12)
    mycsv.writecsv([[], [], ['Summary of %s' % (input_file_1,)], []] + summary_mat1, err_file, 'a')
    summary_mat2 = hdict2matrix(th_order, summary_dict22)
    mycsv.writecsv([[], [], ['Summary of %s' % (input_file_2,)], []] + summary_mat2, err_file, 'a')

    # Convert the absolute and relative differences of the summaries and write them to the error file
    abs_diff_summary_dict[t_key] = [sl + ':' for sl in list(summary_labels)]
    abs_diff_summary_mat = hdict2matrix(tdh_order, abs_diff_summary_dict)
    mycsv.writecsv([[], [], ['Absolute difference in Summary of %s and Summary of %s' % (input_file_1, input_file_2)],
                    []] + abs_diff_summary_mat, err_file, 'a')
    rel_diff_summary_dict[t_key] = [sl + ':' for sl in list(summary_labels)]
    rel_diff_summary_mat = hdict2matrix(tdh_order, rel_diff_summary_dict)
    mycsv.writecsv([[], [], ['Relative difference in Summary of %s and Summary of %s' % (input_file_1, input_file_2)],
                    []] + rel_diff_summary_mat, err_file, 'a')

    return diff_type, num_records, num_big, num_small


def main(argv=None):  # pragma: no cover
    if argv is None:
        argv = sys.argv
    try:
        opts, args = getopt.getopt(argv[1:], "ho:v", ["help", "output="])
    except getopt.error as msg:
        info(sys.argv[0].split("/")[-1] + ": " + str(msg) + "\n\t for help use --help")
        return -1

    # Test for correct number of arguments
    prog_name = os.path.basename(sys.argv[0])
    if len(args) == 6:
        [csv1, csv2, abs_diff_file, rel_diff_file, err_file, csv_summary] = args
    else:
        info('%s: incorrect operands: Try %s -h for more info' % (prog_name, prog_name))
        return -1

    if csv1[-4:] != '.csv' or csv1[-7:] == 'Map.csv' or csv1[-9:] == 'Table.csv' or csv1[-10:] == 'Screen.csv':
        info('%s: input file <%s> with improper extension' % (prog_name, csv1))
        return -1

    if csv2[-4:] != '.csv' or csv2[-7:] == 'Map.csv' or csv2[-9:] == 'Table.csv' or csv2[-10:] == 'Screen.csv':
        info('%s: input file <%s> with improper extension' % (prog_name, csv2))
        return -1

    # Load diffing threshold dictionary
    thresh_dict = ThreshDict(os.path.join(script_dir, 'math_diff.config'))

    math_diff(thresh_dict, csv1, csv2, abs_diff_file, rel_diff_file, err_file, csv_summary)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

# TODO document what happens when there is a time mismatch.

# how the program will respond when the headers of the two csv file do not match
# ------------------------------------------------------------------------------
# The csv files are in the following format:
# "time", "h2", "h3", "h4"
# "t1",  1  ,  2  ,  4
# "t2",  11 ,  22 ,  44
# "t3",  111,  222,  444
#
# In the first line
#     "h2", "h3", "h4"
# are considered the headers of the columns
#
# When we compare two files, it is assumed that the headers of the two files will match.
# In case the headers do not match mathdiff.py still has to respond in an intelligent way.
#
# We have the following four possibilities:
# 1. identical headers
#     file1 = "h2", "h3", "h4"
#     file2 = "h2", "h3", "h4"
#     this is straight forward: the program will report the outputs in the same order:
#     output = "h2", "h3", "h4"
#     output warning = None
# 2. shuffled headers
#     file1 = "h2", "h3", "h4"
#     file2 = "h3", "h4", "h2"
#     the program will un-shuffle the columns of file2 to match that of file1
#     output = "h2", "h3", "h4"
#     output warning = None
# 3. renamed headers
#     file1 = "h2",  "h3",  "h4"
#     file2 = "hh3", "hh4", "hh2"
#     if both the files have the same number of columns, and they don't happen to be shuffled,
#     the program will assume that the headers in file2 have been renamed
#     output = "h2", "h3", "h4"
#     output warning = warning printed to terminal and to error.csv file
# 4. mismatched headers
#     file1 = "h2", "h3", "h4", "h5", "h6"
#     file2 = "h2", "h3", "h4", "h7"
#     the number of columns in file1 and file2 do not match.
#     The program will report on all the columns in file1 and file2
#     output = "h2", "h3", "h4", "h5", "h6", "h7"
#         columns "h5", "h6", "h7" will report an ERROR
#
#
#
#
# ----------------------------------------------------------------------------------
# data structure for mathdiff.py - to be read if you are planning to update the code
# ----------------------------------------------------------------------------------
#
# the csv file had data in the following format
# "time", "h2", "h3", "h4"
# "t1",  1  ,  2  ,  4
# "t2",  11 ,  22 ,  44
# "t3",  111,  222,  444
#
# the standard python module "csv" has functions that can read this text file in as a nested list.
# I call this nested list a matrix.
#
# The above text file will then read into the following structure
# matrix1 = [['time', ' "h2"', ' "h3"', ' "h4"'],
#          ['t1', '  1  ', '  2  ', '  4'],
#          ['t2', '  11 ', '  22 ', '  44'],
#          ['t3', '  111', '  222', '  444']]
#
# Each item in the matrix is a row.
# Each item in the row is a cell.
#
# the time column is stripped from the matrix
# time1, mat1 = slicetime(matrix1)
#
# giving us the matrix
# mat1 = [[' "h2"', ' "h3"', ' "h4"'],
#      ['  1  ', '  2  ', '  4'],
#      ['  11 ', '  22 ', '  44'],
#      ['  111', '  222', '  444']]
#
# mat1 is then converted into a dictionary:
# hdict1 = matrix2hdict(mat1)
#
# hdict1 = {' "h2"': ['  1  ', '  11 ', '  111'],
#      ' "h3"': ['  2  ', '  22 ', '  222'],
#      ' "h4"': ['  4', '  44', '  444']}
#
# Let us call hdict1 the "header dict"
# - the headers of the columns in the csv file become keys of the dictionary.
# - the values of the dictionary are the columns under the header
#
# All calculations are done using "header dict" data structure
# the results of the calculations are returned as a "header dict"
# the "header dict" is converted to a matrix which is then converted a csv text file
#
# ----------------------------------------------------------------------------------
# Structure of the output files
# ----------------------------------------------------------------------------------
#
