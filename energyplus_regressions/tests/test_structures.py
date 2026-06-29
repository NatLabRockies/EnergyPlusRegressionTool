import json
from pathlib import Path
from datetime import datetime
import tempfile
import unittest

from energyplus_regressions.structures import (
    TextDifferences,
    MathDifferences,
    TableDifferences,
    EndErrSummary,
    TestEntry,
    CompletedStructure,
    ForceRunType,
    ReportingFreq
)


class TestForceRunType(unittest.TestCase):

    def test_get_all(self):
        self.assertIsInstance(ForceRunType.get_all(), list)


class TestReportingFrequency(unittest.TestCase):

    def test_get_all(self):
        self.assertIsInstance(ReportingFreq.get_all(), list)


class TestTextDifferences(unittest.TestCase):

    def test_type_to_string(self):
        result = TextDifferences.diff_type_to_string(TextDifferences.EQUAL)
        self.assertIsInstance(result, str)
        result = TextDifferences.diff_type_to_string(TextDifferences.DIFFS)
        self.assertIsInstance(result, str)
        with self.assertRaises(Exception):
            TextDifferences.diff_type_to_string(-1000)

    def test_instance_to_dict(self):
        t = TextDifferences(diff_type=TextDifferences.DIFFS)
        obj = t.to_dict()
        self.assertIn('diff_type', obj)


class TestMathDifferences(unittest.TestCase):

    def test_construct_from_list(self):
        from_math_diff = ['some_diffs', '8 records', '2 big diffs', '3 small diffs']
        MathDifferences(from_math_diff)  # should just pass, nothing to check really

    def test_instance_to_dict(self):
        from_math_diff = ['some_diffs', '8 records', '2 big diffs', '3 small diffs']
        m = MathDifferences(from_math_diff)
        obj = m.to_dict()
        self.assertIn('diff_type', obj)
        self.assertIn('num_records', obj)
        self.assertIn('count_of_big_diff', obj)
        self.assertIn('count_of_small_diff', obj)


class TestTableDifferences(unittest.TestCase):

    def test_construct_from_list(self):
        from_table_diff = [
            'msg',  # 'msg',
            20,  # 'tbl_count',
            2,  # '2 big diffs',
            3,  # '3 small diffs',
            2,  # '2 equal',
            2,  # '2 strings',
            '',  # 'size_err',
            1,  # 1,
            1,  # 1
        ]
        t = TableDifferences(from_table_diff)
        self.assertEqual(2, t.big_diff_count)

    def test_instance_to_dict(self):
        from_table_diff = ['msg', 'tbl_count', '2 big diffs', '3 small diffs', '2 equal', '2 strings', 'size_err', 1, 1]
        t = TableDifferences(from_table_diff)
        obj = t.to_dict()
        self.assertIn('msg', obj)
        self.assertIn('table_count', obj)
        self.assertIn('big_diff_count', obj)
        self.assertIn('small_diff_count', obj)
        self.assertIn('reordered_table_count', obj)

    def test_instance_to_dict_with_reordered_tables(self):
        from_table_diff = ['msg', 'tbl_count', 0, 0, 2, 0, 0, 0, 0, 1]
        t = TableDifferences(from_table_diff)
        obj = t.to_dict()
        self.assertEqual(1, obj['reordered_table_count'])


class TestEndErrSummary(unittest.TestCase):

    def test_status_to_string(self):
        result = EndErrSummary.status_to_string(EndErrSummary.STATUS_UNKNOWN)
        self.assertIsInstance(result, str)
        result = EndErrSummary.status_to_string(EndErrSummary.STATUS_SUCCESS)
        self.assertIsInstance(result, str)
        result = EndErrSummary.status_to_string(EndErrSummary.STATUS_MISSING)
        self.assertIsInstance(result, str)
        result = EndErrSummary.status_to_string(EndErrSummary.STATUS_FATAL)
        self.assertIsInstance(result, str)
        with self.assertRaises(Exception):
            EndErrSummary.status_to_string(-1000)

    def test_instance_to_dict_successful(self):
        e = EndErrSummary(EndErrSummary.STATUS_SUCCESS, 2, EndErrSummary.STATUS_SUCCESS, -1)
        obj = e.to_dict()
        self.assertIn('simulation_status_case1', obj)
        self.assertIn('run_time_seconds_case1', obj)
        self.assertIn('simulation_status_case2', obj)
        self.assertIn('run_time_seconds_case2', obj)

    def test_instance_to_dict_failure(self):
        e = EndErrSummary(EndErrSummary.STATUS_FATAL, -1, EndErrSummary.STATUS_MISSING, -1)
        obj = e.to_dict()
        self.assertIn('simulation_status_case1', obj)
        self.assertNotIn('run_time_seconds_case1', obj)  # won't be for unsuccessful runs
        self.assertIn('simulation_status_case2', obj)
        self.assertNotIn('run_time_seconds_case2', obj)  # won't be for unsuccessful runs


class TestTestEntry(unittest.TestCase):

    @staticmethod
    def fully_populated_entry_successful(t):
        t.add_summary_result(EndErrSummary(EndErrSummary.STATUS_SUCCESS, 1, EndErrSummary.STATUS_SUCCESS, 1))
        t.add_math_differences(MathDifferences([1, 2, 3, 4]), MathDifferences.ESO)
        t.add_math_differences(MathDifferences([1, 2, 3, 4]), MathDifferences.MTR)
        t.add_math_differences(MathDifferences([1, 2, 0, 4]), MathDifferences.ZSZ)
        t.add_math_differences(MathDifferences([1, 2, 3, 4]), MathDifferences.SSZ)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.AUD)
        t.add_text_differences(TextDifferences(TextDifferences.DIFFS), TextDifferences.BND)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.DXF)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.EIO)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.ERR)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.MDD)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.MTD)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.RDD)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.SHD)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.DL_IN)
        t.add_text_differences(TextDifferences(TextDifferences.EQUAL), TextDifferences.DL_OUT)
        t.add_table_differences(TableDifferences([1, 1, 1, 1, 1, 1, 1, 1, 1]))
        return t

    @staticmethod
    def fully_populated_entry_failure(t):
        t.add_summary_result(EndErrSummary(EndErrSummary.STATUS_MISSING, 1, EndErrSummary.STATUS_FATAL, 1))
        return t

    def test_workflow(self):
        t = TestEntry('filename', 'weather')
        self.assertIsNone(t.summary_result)
        self.assertIsNone(t.eso_diffs)
        self.assertIsNone(t.mtr_diffs)
        self.assertIsNone(t.zsz_diffs)
        self.assertIsNone(t.ssz_diffs)
        self.assertIsNone(t.aud_diffs)
        self.assertIsNone(t.bnd_diffs)
        self.assertIsNone(t.dxf_diffs)
        self.assertIsNone(t.eio_diffs)
        self.assertIsNone(t.err_diffs)
        self.assertIsNone(t.mdd_diffs)
        self.assertIsNone(t.mtd_diffs)
        self.assertIsNone(t.rdd_diffs)
        self.assertIsNone(t.shd_diffs)
        self.assertIsNone(t.dl_in_diffs)
        self.assertIsNone(t.dl_out_diffs)
        self.assertIsNone(t.table_diffs)
        t = TestTestEntry.fully_populated_entry_successful(t)
        self.assertIsNotNone(t.summary_result)
        self.assertIsNotNone(t.eso_diffs)
        self.assertIsNotNone(t.mtr_diffs)
        self.assertIsNotNone(t.zsz_diffs)
        self.assertIsNotNone(t.ssz_diffs)
        self.assertIsNotNone(t.aud_diffs)
        self.assertIsNotNone(t.bnd_diffs)
        self.assertIsNotNone(t.dxf_diffs)
        self.assertIsNotNone(t.eio_diffs)
        self.assertIsNotNone(t.err_diffs)
        self.assertIsNotNone(t.mdd_diffs)
        self.assertIsNotNone(t.mtd_diffs)
        self.assertIsNotNone(t.rdd_diffs)
        self.assertIsNotNone(t.shd_diffs)
        self.assertIsNotNone(t.dl_in_diffs)
        self.assertIsNotNone(t.dl_out_diffs)
        self.assertIsNotNone(t.dl_out_diffs)
        obj = t.to_dict()
        self.assertIsInstance(obj, dict)


class TestCompletedStructure(unittest.TestCase):

    def test_workflow(self):
        c = CompletedStructure(
            Path('/a/source/dir'), Path('/a/build/dir'),
            Path('/b/source/dir'), Path('/b/build/dir'),
            Path('/r/dir1'), Path('/r/dir2'),
            datetime.now()
        )
        t = TestEntry('filename', 'weather')
        t = TestTestEntry.fully_populated_entry_successful(t)
        c.add_test_entry(t)
        t = TestEntry('file_that_failed', 'weather')
        t = TestTestEntry.fully_populated_entry_failure(t)
        c.add_test_entry(t)
        t = TestEntry('filename', 'weather')
        t = TestTestEntry.fully_populated_entry_successful(t)
        # override the table data, put 2 string diffs so one is caught
        t.add_table_differences(TableDifferences([1, 1, 0, 1, 1, 2, 1, 1, 1]))
        c.add_test_entry(t)

    def test_to_csv(self):
        c = CompletedStructure(
            Path('/a/source/dir'), Path('/a/build/dir'),
            Path('/b/source/dir'), Path('/b/build/dir'),
            Path('/r/dir1'), Path('/r/dir2'),
            datetime.now()
        )
        t = TestEntry('filename', 'weather')
        t = TestTestEntry.fully_populated_entry_successful(t)
        c.add_test_entry(t)
        valid_temp_csv_file = Path(tempfile.mkstemp(suffix='.csv')[1])
        c.to_runtime_summary(valid_temp_csv_file)  # not asserting anything, it should just pass
        with self.assertRaises(Exception):
            c.to_runtime_summary(Path('/invalid/path'))

    def test_to_json(self):
        c = CompletedStructure(
            Path('/a/source/dir'), Path('/a/build/dir'),
            Path('/b/source/dir'), Path('/b/build/dir'),
            Path('/r/dir1'), Path('/r/dir2'),
            datetime.now()
        )
        t = TestEntry('filename', 'weather')
        t = TestTestEntry.fully_populated_entry_successful(t)
        c.add_test_entry(t)
        valid_temp_json_file = Path(tempfile.mkstemp(suffix='.json')[1])
        c.to_json_summary(valid_temp_json_file)
        with open(valid_temp_json_file) as f:
            json_body = f.read()
            obj = json.loads(json_body)
            self.assertIn('directories', obj)
            self.assertIn('runs', obj)
            self.assertIn('diffs', obj)
            self.assertIn('results_by_file', obj)

    def test_to_json_object_response(self):
        c = CompletedStructure(
            Path('/a/source/dir'), Path('/a/build/dir'),
            Path('/b/source/dir'), Path('/b/build/dir'),
            Path('/r/dir1'), Path('/r/dir2'),
            datetime.now()
        )
        t = TestEntry('filename', 'weather')
        t = TestTestEntry.fully_populated_entry_successful(t)
        c.add_test_entry(t)
        obj = c.to_json_summary()
        self.assertIn('directories', obj)
        self.assertIn('runs', obj)
        self.assertIn('diffs', obj)
        self.assertIn('results_by_file', obj)

    def test_to_json_summary_reports_single_table_string_diff_as_big_table(self):
        c = CompletedStructure(
            Path('/a/source/dir'), Path('/a/build/dir'),
            Path('/b/source/dir'), Path('/b/build/dir'),
            Path('/r/dir1'), Path('/r/dir2'),
            datetime.now()
        )
        t = TestEntry('filename', 'weather')
        t.add_summary_result(EndErrSummary(EndErrSummary.STATUS_SUCCESS, 1, EndErrSummary.STATUS_SUCCESS, 1))
        t.add_table_differences(TableDifferences(['', 1, 0, 0, 2, 1, 0, 0, 0]))
        c.add_test_entry(t)

        obj = c.to_json_summary()

        self.assertEqual(['filename'], obj['diffs']['big_table'])
        self.assertEqual([], obj['diffs']['small_table'])
        self.assertEqual(1, obj['results_by_file'][0]['table_diffs']['string_diff_count'])

    def test_to_json_summary_does_not_report_reordered_only_table_as_diff(self):
        c = CompletedStructure(
            Path('/a/source/dir'), Path('/a/build/dir'),
            Path('/b/source/dir'), Path('/b/build/dir'),
            Path('/r/dir1'), Path('/r/dir2'),
            datetime.now()
        )
        t = TestEntry('filename', 'weather')
        t.add_summary_result(EndErrSummary(EndErrSummary.STATUS_SUCCESS, 1, EndErrSummary.STATUS_SUCCESS, 1))
        t.add_table_differences(TableDifferences(['', 1, 0, 0, 2, 0, 0, 0, 0, 1]))
        c.add_test_entry(t)

        obj = c.to_json_summary()

        self.assertEqual([], obj['diffs']['big_table'])
        self.assertEqual([], obj['diffs']['small_table'])
        self.assertEqual(1, obj['results_by_file'][0]['table_diffs']['reordered_table_count'])
