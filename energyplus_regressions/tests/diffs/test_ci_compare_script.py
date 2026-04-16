import glob
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import skipIf
from contextlib import contextmanager

try:
    from cStringIO import StringIO  # Python 2, ensures that the overridden bytes-based-stdout is still bytes-based
except ImportError:
    from io import StringIO  # Python 3, will use unicode based overridden stdout

from energyplus_regressions.diffs.ci_compare_script import cleanup, get_diff_files, main_function, print_message, \
    process_diffs
from energyplus_regressions.runtests import TestEntry
from energyplus_regressions.structures import MathDifferences


@contextmanager
def captured_output():
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err


class TestCICompareScriptFunctions(unittest.TestCase):

    def setUp(self):
        self.cur_dir_path = Path(__file__).resolve().parent
        self.csv_resource_dir = self.cur_dir_path / 'csv_resources'
        self.tbl_resource_dir = self.cur_dir_path / 'tbl_resources'
        self.temp_dir = Path(tempfile.mkdtemp())
        self.temp_base_dir = Path(tempfile.mkdtemp())
        self.temp_mod_dir = Path(tempfile.mkdtemp())

    def test_get_diff_files(self):
        file_names = [
            'eplusout.rdd',
            'eplusout.rdd.diffs',
            'eplusout.csv',
            'eplusout.csv.absdiffs.csv'
        ]
        for file_name in file_names:
            full_path = os.path.join(self.temp_dir, file_name)
            with open(full_path, 'w'):
                pass  # just let it close the file
        self.assertEqual(2, len(get_diff_files(self.temp_dir)))

    def test_cleanup(self):
        file_names = [
            'eplusout.rdd',
            'eplusout.rdd.diffs',
            'eplusout.csv',
            'eplusout.csv.absdiffs.csv'
        ]
        for file_name in file_names:
            full_path = self.temp_dir / file_name
            with open(full_path, 'w'):
                pass  # just let it close the file
        files_found = glob.glob(os.path.join(self.temp_dir, "*"))
        self.assertEqual(4, len(files_found))
        cleanup(self.temp_dir)
        files_found = glob.glob(os.path.join(self.temp_dir, "*"))
        self.assertEqual(2, len(files_found))

    def test_print_message(self):
        with captured_output() as (out, err):
            print_message("Hello world!")
        # This can go inside or outside the `with` block
        output = out.getvalue().strip()
        self.assertIn('decent_ci:test_result:message', output)
        self.assertIn('Hello', output)

    def test_process_diffs(self):
        # process diffs should never turn a True to a False!
        entry = TestEntry('MyFileName', 'MyWeather.epw')
        # try a blank entry
        initial_has_diffs = False
        initial_has_small_diffs = False
        new_diffs, new_small_diffs = process_diffs("ESO", entry.eso_diffs, initial_has_diffs, initial_has_small_diffs)
        self.assertFalse(new_diffs)
        self.assertFalse(new_small_diffs)
        # now add some only small diff to it
        entry.add_math_differences(MathDifferences(['Small Diffs', 2, 0, 4]), MathDifferences.ESO)
        with captured_output() as (out, err):
            new_diffs, new_small_diffs = process_diffs("ESO", entry.eso_diffs, new_diffs, new_small_diffs)
            self.assertFalse(new_diffs)
            self.assertTrue(new_small_diffs)
            self.assertIn('ESO small diffs', out.getvalue().strip())
        # now add some only big diff to it
        new_small_diffs = False
        new_diffs = False
        entry.add_math_differences(MathDifferences(['Big Diffs', 2, 3, 0]), MathDifferences.ESO)
        with captured_output() as (out, err):
            new_diffs, new_small_diffs = process_diffs("ESO", entry.eso_diffs, new_diffs, new_small_diffs)
            self.assertTrue(new_diffs)
            self.assertFalse(new_small_diffs)
            self.assertIn('ESO big diffs', out.getvalue().strip())
        # now go back to a blank one, any True values should still be True!
        entry.eso_diffs = None
        new_diffs, new_small_diffs = process_diffs("ESO", entry.eso_diffs, new_diffs, new_small_diffs)
        self.assertTrue(new_diffs)
        self.assertFalse(new_small_diffs)

    def _write_files_to_both_folders(self, file_name, output_base, output_mod):
        with open(os.path.join(self.temp_base_dir, file_name), 'w') as f1:
            f1.write(output_base)
        with open(os.path.join(self.temp_mod_dir, file_name), 'w') as f1:
            f1.write(output_mod)

    def test_main_function(self):
        # should fail if we don't have any .end files
        with captured_output() as (out, err):
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=Path(self.temp_base_dir),
                mod_dir=Path(self.temp_mod_dir),
                base_sha='base123',
                mod_sha='mod456',
                _make_public=True,
                device_id='some_device_id',
                test_mode=True
            )
            self.assertIn('Skipping', out.getvalue().strip())
        # now write out a bunch of diff files and make sure the output is good to go
        end_string = 'EnergyPlus Completed Successfully-- 0 Warning; 0 Severe Errors; Elapsed Time=00hr 00min  3.06sec'
        self._write_files_to_both_folders('eplusout.end', end_string, end_string)
        # test one set of results where there is just table small diffs
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl.htm'),
            os.path.join(self.temp_base_dir, 'eplustbl.htm')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_small_numeric_diff.htm'),
            os.path.join(self.temp_mod_dir, 'eplustbl.htm')
        )
        with captured_output() as (out, err):
            # should fail if we don't have any .end files
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=self.temp_base_dir,
                mod_dir=self.temp_mod_dir,
                base_sha='base123',
                mod_sha='mod456',
                _make_public=True,
                device_id='some_device_id',
                test_mode=True
            )
            self.assertIn('Table small diffs', out.getvalue().strip())

    def test_main_function_reports_single_table_string_diff(self):
        end_string = 'EnergyPlus Completed Successfully-- 0 Warning; 0 Severe Errors; Elapsed Time=00hr 00min  3.06sec'
        self._write_files_to_both_folders('eplusout.end', end_string, end_string)
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_string_diff_base.htm'),
            os.path.join(self.temp_base_dir, 'eplustbl.htm')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_string_diff_mod.htm'),
            os.path.join(self.temp_mod_dir, 'eplustbl.htm')
        )
        with captured_output() as (out, err):
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=self.temp_base_dir,
                mod_dir=self.temp_mod_dir,
                base_sha='base123',
                mod_sha='mod456',
                _make_public=True,
                device_id='some_device_id',
                test_mode=True
            )
            output = out.getvalue().strip()
            self.assertIn('Table string diffs', output)
            self.assertNotIn('Table big diffs', output)
            self.assertNotIn('Table small diffs', output)
        # now test one where every single file has big diffs
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'eplusout.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'eplusout.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'eplusmtr.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'eplusmtr.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'epluszsz.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'epluszsz.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'eplusssz.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'eplusssz.csv')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_big_numeric_diff_and_string_diff_base.htm'),
            os.path.join(self.temp_base_dir, 'eplustbl.htm')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_big_numeric_diff_and_string_diff_mod.htm'),
            os.path.join(self.temp_mod_dir, 'eplustbl.htm')
        )
        self._write_files_to_both_folders('eplusout.audit', 'base audit output', 'mod audit output')
        self._write_files_to_both_folders('eplusout.bnd', 'base bnd output', 'mod bnd output')
        self._write_files_to_both_folders('eplusout.dxf', 'base dxf output', 'mod dxf output')
        self._write_files_to_both_folders('eplusout.eio', 'base eio output', 'mod eio output')
        self._write_files_to_both_folders('eplusout.mdd', 'base mdd output', 'mod mdd output')
        self._write_files_to_both_folders('eplusout.mtd', 'base mtd output', 'mod mtd output')
        self._write_files_to_both_folders('eplusout.rdd', 'base rdd output', 'mod rdd output')
        self._write_files_to_both_folders('eplusout.shd', 'base shd output', 'mod shd output')
        self._write_files_to_both_folders('eplusout.err', 'base err output', 'mod err output')
        self._write_files_to_both_folders('eplusout.delightin', 'base delightin output', 'mod delightin output')
        self._write_files_to_both_folders('eplusout.delightout', 'base delightout output', 'mod delightout output')
        self._write_files_to_both_folders('readvars.audit', 'base readvars audit output', 'mod readvars audit output')
        self._write_files_to_both_folders('eplusout.edd', 'base edd output', 'mod edd output')
        self._write_files_to_both_folders('eplusout.wrl', 'base wrl output', 'mod wrl output')
        self._write_files_to_both_folders('eplusout.sln', 'base sln output', 'mod sln output')
        self._write_files_to_both_folders('eplusout.sci', 'base sci output', 'mod sci output')
        self._write_files_to_both_folders('eplusmap.csv', 'base map output', 'mod map output')
        self._write_files_to_both_folders('eplusout.dfs', 'base dfs output', 'mod dfs output')
        self._write_files_to_both_folders('eplusscreen.csv', 'base screen output', 'mod screen output')
        self._write_files_to_both_folders('eplusout.glhe', '{"glhe_1":{}}', '{"glhe 2":{}}')
        self._write_files_to_both_folders('eplusout_hourly.json', '{"hi":{}}', '{"bye":{}}')
        self._write_files_to_both_folders('in.idf', 'base idf content', 'mod idf content')
        self._write_files_to_both_folders('eplusout.stdout', 'base standard output', 'mod standard output')
        self._write_files_to_both_folders('eplusout.stderr', 'base standard error', 'mod standard error')
        self._write_files_to_both_folders('eplusout_perflog.csv', 'a,b,c,4\nd,e,f,4', 'a,b,c,4\nq,e,g,3')
        with captured_output() as (out, err):
            # should fail if we don't have any .end files
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=self.temp_base_dir,
                mod_dir=self.temp_mod_dir,
                base_sha='base124',
                mod_sha='mod457',
                _make_public=True,
                device_id='some_device_id',
                test_mode=True
            )
            expected_tokens = [
                'AUD diffs',
                'BND diffs',
                'delightin diffs',
                'delightout diffs',
                'DXF diffs',
                'EIO diffs',
                'ERR diffs',
                'ESO big diffs',
                'MDD diffs',
                'MTD diffs',
                'MTR big diffs',
                'RDD diffs',
                'SHD diffs',
                'SSZ big diffs',
                'ZSZ big diffs',
                'Table big diffs',
                'Table string diffs',
                'ReadvarsAudit diffs',
                'EDD diffs',
                'WRL diffs',
                'SLN diffs',
                'SCI diffs',
                'MAP diffs',
                'DFS diffs',
                'SCREEN diffs',
                'GLHE diffs',
                'JSON big diffs',
                '[decent_ci:test_result:warn]',
                'IDF diffs',
                'StdOut diffs',
                'StdErr diffs',
                'PERF_LOG diffs'
            ]
            output = out.getvalue().strip()
            for token in expected_tokens:
                self.assertIn(token, output)

    @skipIf(True, 'Running this test requires Amazon credentials on the machine')
    def test_main_function_not_test_mode(self):  # pragma: no cover
        # should fail if we don't have any .end files
        with captured_output() as (out, err):
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=self.temp_base_dir,
                mod_dir=self.temp_mod_dir,
                base_sha='base123',
                mod_sha='mod456',
                _make_public=True,
                device_id='some_device_id',
                test_mode=True
            )
            self.assertIn('Skipping', out.getvalue().strip())
        # now write out a bunch of diff files and make sure the output is good to go
        end_string = 'EnergyPlus Completed Successfully-- 0 Warning; 0 Severe Errors; Elapsed Time=00hr 00min  3.06sec'
        self._write_files_to_both_folders('eplusout.end', end_string, end_string)
        # test one set of results there there is just table small diffs
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl.htm'),
            os.path.join(self.temp_base_dir, 'eplustbl.htm')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_small_numeric_diff.htm'),
            os.path.join(self.temp_mod_dir, 'eplustbl.htm')
        )
        with captured_output() as (out, err):
            # should fail if we don't have any .end files
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=self.temp_base_dir,
                mod_dir=self.temp_mod_dir,
                base_sha='base123',
                mod_sha='mod456',
                _make_public=True,
                device_id='some_device_id',
                test_mode=True
            )
            self.assertIn('Table small diffs', out.getvalue().strip())
        # now test one where every single file has big diffs
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'eplusout.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'eplusout.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'eplusmtr.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'eplusmtr.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'epluszsz.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'epluszsz.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout.csv'),
            os.path.join(self.temp_base_dir, 'eplusssz.csv')
        )
        shutil.copy(
            os.path.join(self.csv_resource_dir, 'eplusout_big_watt_diffs.csv'),
            os.path.join(self.temp_mod_dir, 'eplusssz.csv')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl.htm'),
            os.path.join(self.temp_base_dir, 'eplustbl.htm')
        )
        shutil.copy(
            os.path.join(self.tbl_resource_dir, 'eplustbl_has_big_numeric_diff.htm'),
            os.path.join(self.temp_mod_dir, 'eplustbl.htm')
        )
        self._write_files_to_both_folders('eplusout.audit', 'base audit output', 'mod audit output')
        self._write_files_to_both_folders('eplusout.bnd', 'base bnd output', 'mod bnd output')
        self._write_files_to_both_folders('eplusout.dxf', 'base dxf output', 'mod dxf output')
        self._write_files_to_both_folders('eplusout.eio', 'base eio output', 'mod eio output')
        self._write_files_to_both_folders('eplusout.mdd', 'base mdd output', 'mod mdd output')
        self._write_files_to_both_folders('eplusout.mtd', 'base mtd output', 'mod mtd output')
        self._write_files_to_both_folders('eplusout.rdd', 'base rdd output', 'mod rdd output')
        self._write_files_to_both_folders('eplusout.shd', 'base shd output', 'mod shd output')
        self._write_files_to_both_folders('eplusout.err', 'base err output', 'mod err output')
        self._write_files_to_both_folders('eplusout.delightin', 'base delightin output', 'mod delightin output')
        self._write_files_to_both_folders('eplusout.delightout', 'base delightout output', 'mod delightout output')
        with captured_output() as (out, err):
            # should fail if we don't have any .end files
            main_function(
                file_name='HVACTemplate-5ZoneFanCoil',
                base_dir=self.temp_base_dir,
                mod_dir=self.temp_mod_dir,
                base_sha='base123',
                mod_sha='mod456',
                _make_public=True,
                device_id='some_device_id',
                test_mode=False
            )
            expected_tokens = [
                'AUD diffs',
                'BND diffs',
                'delightin diffs',
                'delightout diffs',
                'DXF diffs',
                'EIO diffs',
                'ERR diffs',
                'ESO big diffs',
                'MDD diffs',
                'MTD diffs',
                'MTR big diffs',
                'RDD diffs',
                'SHD diffs',
                'SSZ big diffs',
                'ZSZ big diffs',
                'Table big diffs',
                '[decent_ci:test_result:warn]',
                'Regression Results'
            ]
            output = out.getvalue().strip()
            for token in expected_tokens:
                self.assertIn(token, output)
