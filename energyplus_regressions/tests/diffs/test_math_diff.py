import os
import tempfile
import unittest

from energyplus_regressions.diffs.math_diff import math_diff, DuplicateHeaderException
from energyplus_regressions.diffs.thresh_dict import ThreshDict


class TestMathDiff(unittest.TestCase):

    def setUp(self):
        self.cur_dir_path = os.path.dirname(os.path.realpath(__file__))
        self.diff_files_dir = os.path.join(self.cur_dir_path, 'csv_resources')
        self.temp_output_dir = tempfile.mkdtemp()
        self.thresh_dict = ThreshDict(os.path.join(self.diff_files_dir, 'test_math_diff.config'))

    def test_identical_files(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('All Equal', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_identical_totally_empty_files(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout_totally_empty.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_totally_empty.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('malformed or empty csv file', response[0])
        self.assertEqual(0, response[1])
        self.assertEqual(0, response[2])
        self.assertEqual(0, response[3])

    def test_identical_empty_data_files(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout_empty_data.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_empty_data.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('has no data', response[0])
        self.assertEqual(0, response[1])
        self.assertEqual(0, response[2])
        self.assertEqual(0, response[3])

    def test_identical_duplicate_header_fails(self):
        with self.assertRaises(DuplicateHeaderException):
            math_diff(
                self.thresh_dict,
                os.path.join(self.diff_files_dir, 'eplusout_duplicate_header.csv'),
                os.path.join(self.diff_files_dir, 'eplusout_duplicate_header.csv'),
                os.path.join(self.temp_output_dir, 'abs_diff.csv'),
                os.path.join(self.temp_output_dir, 'rel_diff.csv'),
                os.path.join(self.temp_output_dir, 'math_diff.log'),
                os.path.join(self.temp_output_dir, 'summary.csv'),
            )

    def test_small_diff_in_watts_files(self):
        """This tests the ability to capture diffs in a regular (not-temperature) variable"""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_small_watt_diffs.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Small Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(2, response[3])  # small diffs

    def test_bad_numeric_raises_exception(self):
        """This tests the ability to handle bad numerics which cause weird errors in MathDiff"""
        with self.assertRaises(KeyError):
            math_diff(
                self.thresh_dict,
                os.path.join(self.diff_files_dir, 'eplusout.csv'),
                os.path.join(self.diff_files_dir, 'eplusout_bad_numeric.csv'),
                os.path.join(self.temp_output_dir, 'abs_diff.csv'),
                os.path.join(self.temp_output_dir, 'rel_diff.csv'),
                os.path.join(self.temp_output_dir, 'math_diff.log'),
                os.path.join(self.temp_output_dir, 'summary.csv'),
            )

    def test_big_diff_in_watts_files(self):
        """This tests the ability to capture diffs in a regular (not-temperature) variable"""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Big Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(2, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_small_diff_in_temp_files(self):
        """This tests the ability to capture diffs in a temperature variable - where relative threshold isn't used"""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_small_temp_diffs.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Small Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(1, response[3])  # small diffs

    def test_big_diff_in_temp_files(self):
        """This tests the ability to capture diffs in a temperature variable - where relative threshold isn't used"""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_big_temp_diffs.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Big Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(1, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_mixed_diffs(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_mixed_diffs.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Big Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(2, response[2])  # big diffs
        self.assertEqual(5, response[3])  # small diffs

    def test_changed_column_order_equal(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_change_column_order.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('All Equal', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_changed_column_order_diffs(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_change_column_order_diffs.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Big Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(2, response[2])  # big diffs
        self.assertEqual(1, response[3])  # small diffs

    def test_changed_timestamps(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_changed_timestamps.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertEqual('Time series do not match', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_empty_data_file_1(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout_empty_data.csv'),
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('has no data', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_empty_data_file_2(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_empty_data.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('has no data', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_totally_empty_file_1(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout_totally_empty.csv'),
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('empty', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_totally_empty_file_2(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_totally_empty.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('empty', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_invalid_file_1(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout_DOESNOTEXIST.csv'),
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('unable to open file', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_invalid_file_2(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_DOESNOTEXIST.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('unable to open file', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_duplicate_header_fails(self):
        with self.assertRaises(DuplicateHeaderException):
            math_diff(
                self.thresh_dict,
                os.path.join(self.diff_files_dir, 'eplusout.csv'),
                os.path.join(self.diff_files_dir, 'eplusout_duplicate_header.csv'),
                os.path.join(self.temp_output_dir, 'abs_diff.csv'),
                os.path.join(self.temp_output_dir, 'rel_diff.csv'),
                os.path.join(self.temp_output_dir, 'math_diff.log'),
                os.path.join(self.temp_output_dir, 'summary.csv'),
            )

    def test_data_with_holes(self):
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_with_data_holes.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('Big Diffs', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(1, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_data_with_more_data_than_headers(self):
        """I don't know how we could get to this situation, but anyway, this tests to ensure that if a file has
        more data columns than header columns, the data after the last header column is ignored.  A diff is encountered
        in the extra column, but it should be ignored."""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_more_data_than_headers.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('All Equal', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_data_with_totally_different_headers(self):
        """Two files that don't have _any_ common headers shouldn't work"""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_totally_different_headers.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('No common fields', response[0])  # diff status
        self.assertEqual(0, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs

    def test_data_with_extra_column_in_case_2(self):
        """If file 2 has extra columns, the comparison should still work but extra outputs will be ignored"""
        response = math_diff(
            self.thresh_dict,
            os.path.join(self.diff_files_dir, 'eplusout.csv'),
            os.path.join(self.diff_files_dir, 'eplusout_extra_column.csv'),
            os.path.join(self.temp_output_dir, 'abs_diff.csv'),
            os.path.join(self.temp_output_dir, 'rel_diff.csv'),
            os.path.join(self.temp_output_dir, 'math_diff.log'),
            os.path.join(self.temp_output_dir, 'summary.csv'),
        )
        self.assertIn('All Equal', response[0])  # diff status
        self.assertEqual(24, response[1])  # num records compared
        self.assertEqual(0, response[2])  # big diffs
        self.assertEqual(0, response[3])  # small diffs
