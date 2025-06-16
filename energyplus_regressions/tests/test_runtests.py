import json
from pathlib import Path
from platform import system
import shutil
import tempfile
import unittest

from energyplus_regressions.builds.makefile import CMakeCacheMakeFileBuildDirectory
from energyplus_regressions.runtests import TestRunConfiguration, SuiteRunner
from energyplus_regressions.structures import (
    EndErrSummary, ForceRunType, ForceOutputSQL, ForceOutputSQLUnitConversion,
    ReportingFreq, TestEntry, TextDifferences
)


class TestTestSuiteRunner(unittest.TestCase):

    def setUp(self):
        self.cur_dir_path = Path(__file__).resolve().parent
        self.resources = self.cur_dir_path / 'resources'
        self.temp_base_source_dir = Path(tempfile.mkdtemp())
        self.temp_base_build_dir = Path(tempfile.mkdtemp())
        self.temp_mod_source_dir = Path(tempfile.mkdtemp())
        self.temp_mod_build_dir = Path(tempfile.mkdtemp())
        self.temp_csv_file = Path(tempfile.mkstemp(suffix='.csv')[1])

    def establish_build_folder(
            self, target_build_dir: Path, target_source_dir: Path,
            idf_config, idf_in_dir=False, alt_filename=None, py_file=False
    ):
        with (target_build_dir / 'CMakeCache.txt').open('w') as f:
            f.write('HEY\n')
            f.write('CMAKE_HOME_DIRECTORY:INTERNAL=%s\n' % target_source_dir)
            f.write('HEY AGAIN\n')
        products_dir = target_build_dir / 'Products'
        products_dir.mkdir()
        macro_dir = target_source_dir / 'bin' / 'EPMacro' / 'Linux'
        macro_dir.mkdir(parents=True)
        if system() == 'Windows':  # pragma: no cover  -- not running coverage results on Travis on Windows
            # if we are on Windows, we need to prepackage up the python scripts as exe files for them to run
            # properly across interpreters.  Its easy enough to do with pyinstaller, just need to set up a couple
            # variables and run them all.  Also, we don't want to run them for every single test, just once if the dist/
            # folder hasn't been created yet.
            dist_folder = self.resources / 'dist'
            products_map = {
                self.resources / 'dummy.basement.idd': products_dir / 'BasementGHT.idd',
                dist_folder / 'basement.exe': products_dir / 'Basement.exe',
                self.resources / 'dummy.Energy+.idd': products_dir / 'Energy+.idd',
                dist_folder / 'energyplus.exe': products_dir / 'energyplus.exe',
                dist_folder / 'expandobjects.exe': products_dir / 'ExpandObjects.exe',
                dist_folder / 'parametric.exe': products_dir / 'ParametricPreprocessor.exe',
                dist_folder / 'readvars.exe': products_dir / 'ReadVarsESO.exe',
                dist_folder / 'slab.exe': products_dir / 'Slab.exe',
                self.resources / 'dummy.slab.idd': products_dir / 'SlabGHT.idd',
                dist_folder / 'epmacro.exe': macro_dir / 'EPMacro.exe',
            }
        else:
            products_map = {
                self.resources / 'dummy.basement.idd': products_dir / 'BasementGHT.idd',
                self.resources / 'dummy.basement.py': products_dir / 'Basement',
                self.resources / 'dummy.Energy+.idd': products_dir / 'Energy+.idd',
                self.resources / 'dummy.energyplus.py': products_dir / 'energyplus',
                self.resources / 'dummy.expandobjects.py': products_dir / 'ExpandObjects',
                self.resources / 'dummy.parametric.py': products_dir / 'ParametricPreprocessor',
                self.resources / 'dummy.readvars.py': products_dir / 'ReadVarsESO',
                self.resources / 'dummy.slab.py': products_dir / 'Slab',
                self.resources / 'dummy.slab.idd': products_dir / 'SlabGHT.idd',
                self.resources / 'dummy.epmacro.py': macro_dir / 'EPMacro',
            }
        for source in products_map:
            shutil.copy(source, products_map[source])
        testfiles_dir = target_source_dir / 'testfiles'
        testfiles_dir.mkdir()
        json_text = json.dumps(idf_config)
        if idf_in_dir:
            idf_dir = testfiles_dir / 'subdir'
            idf_dir.mkdir()
        else:
            idf_dir = testfiles_dir
        filename = 'my_file.idf'
        if alt_filename:
            filename = alt_filename
        with (idf_dir / filename).open('w') as f:
            f.write(json_text)
        with (testfiles_dir / 'my_file.rvi').open('w') as f_rvi:
            f_rvi.write('RVI TEXT')
        with (testfiles_dir / 'my_file.mvi').open('w') as f_mvi:
            f_mvi.write('MVI TEXT')
        with (testfiles_dir / 'HybridZoneModel_TemperatureData.csv').open('w') as f_hybrid:
            f_hybrid.write('OK')
        with (testfiles_dir / 'SolarShadingTest_Shading_Data.csv').open('w') as f_hybrid:
            f_hybrid.write('OK2')
        with (testfiles_dir / 'LocalEnvData.csv').open('w') as f_hybrid:
            f_hybrid.write('OK3')
        with (testfiles_dir / 'LookupTable.csv').open('w') as f_lookup:
            f_lookup.write('OK4')
        with (testfiles_dir / 'HybridModel_Measurements_with_HVAC.csv').open('w') as f_hybrid:
            f_hybrid.write('OK5')
        with (testfiles_dir / 'HybridModel_Measurements_no_HVAC.csv').open('w') as f_hybrid:
            f_hybrid.write('OK6')
        with (testfiles_dir / 'my_macro_file.imf').open('w') as f_macro:
            f_macro.write(json_text)
        with (testfiles_dir / 'extra.imf').open('w') as f_macro_extra:
            f_macro_extra.write('##MACROTEXT')
        with (testfiles_dir / 'EMSTestMathAndKill.idf').open('w') as f_kill:
            f_kill.write(json_text)
        cbor_files_to_prepare = [
            'CoolSys1-Chiller.RS0001.a205.cbor',
            'A205ExampleChiller.RS0001.a205.cbor',
            'CoolSys1-Chiller-Detailed.RS0001.a205.cbor',
        ]
        for cbor_file_to_prepare in cbor_files_to_prepare:
            with (testfiles_dir / cbor_file_to_prepare).open('w') as f_cbor:
                f_cbor.write('CBOR')
        if py_file:
            with (idf_dir / "my_file.py").open('w') as f:
                f.write("hello")
        weather_dir = target_source_dir / 'weather'
        weather_dir.mkdir()
        shutil.copy(self.resources / 'dummy.in.epw', weather_dir / 'my_weather.epw')
        shutil.copy(
            self.resources / 'dummy.in.epw',
            weather_dir / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
        )
        datasets_dir = target_source_dir / 'datasets'
        datasets_dir.mkdir()
        with (datasets_dir / 'Window5DataFile.dat').open('w') as f_window:
            f_window.write('HI')
        tdv_dir = datasets_dir / 'TDV'
        tdv_dir.mkdir()
        with (tdv_dir / 'dummy.txt').open('w') as f_tdv:
            f_tdv.write('HEY')
        if 'extra_data' in idf_config['config'] and 'ExternalInterface' in idf_config['config']['extra_data']:
            fmu_dir = datasets_dir / 'FMUs'
            fmu_dir.mkdir()
            with (fmu_dir / 'My.fmu').open('w') as f_fmu:
                f_fmu.write('AlgebraicVariables')
        # os.path.join(self.resource_dir, 'dummy.epmacro.py'): os.path.join(products_dir, 'Energy+.idd'),

    @staticmethod
    def dummy_callback(*args, **kwargs):
        pass

    def test_both_success_no_diffs_no_force(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            },
            py_file=True
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have created a run directory for this file, put input files there, and left output files there
        file_results_dir = results_dir / 'my_file'
        self.assertTrue(file_results_dir.exists())
        self.assertTrue((file_results_dir / 'in.epw').exists())
        self.assertTrue((file_results_dir / 'in.idf').exists())
        self.assertTrue((file_results_dir / 'eplusout.eso').exists())
        self.assertTrue((file_results_dir / 'eplusout.end').exists())
        self.assertTrue((file_results_dir / 'eplusout.csv').exists())

        # file in dir A has accompanying python plugin file, so it should be copied in, but not in build B
        self.assertTrue((file_results_dir / 'my_file.py').exists())
        self.assertFalse((diff_results.results_dir_b / 'my_file' / 'my_file.py').exists())

        # check the diffs
        self.assertEqual('All Equal', results_for_file.eso_diffs.diff_type)
        self.assertEqual('All Equal', results_for_file.mtr_diffs.diff_type)
        self.assertEqual('All Equal', results_for_file.ssz_diffs.diff_type)
        self.assertEqual('All Equal', results_for_file.zsz_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.aud_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.bnd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.dl_in_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.dl_out_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.dxf_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.eio_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.err_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.mdd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.mtd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.rdd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.shd_diffs.diff_type)
        # TODO: Check TableDiff

    def test_no_diffs_idf_in_subdirectory(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            },
            True
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            },
            True
        )
        mod.set_build_directory(self.temp_mod_build_dir)
        d = Path('subdir') / 'my_file.idf'
        entries = [TestEntry(str(d), 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('subdir__my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have created a run directory for this file, put input files there, and left output files there
        file_results_dir = results_dir / 'subdir__my_file'
        self.assertTrue(file_results_dir.exists())
        self.assertTrue((file_results_dir / 'in.epw').exists())
        self.assertTrue((file_results_dir / 'in.idf').exists())
        self.assertTrue((file_results_dir / 'eplusout.eso').exists())
        self.assertTrue((file_results_dir / 'eplusout.end').exists())
        self.assertTrue((file_results_dir / 'eplusout.csv').exists())
        # check the diffs
        self.assertEqual('All Equal', results_for_file.eso_diffs.diff_type)
        self.assertEqual('All Equal', results_for_file.mtr_diffs.diff_type)
        self.assertEqual('All Equal', results_for_file.ssz_diffs.diff_type)
        self.assertEqual('All Equal', results_for_file.zsz_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.aud_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.bnd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.dl_in_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.dl_out_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.dxf_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.eio_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.err_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.mdd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.mtd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.rdd_diffs.diff_type)
        self.assertEqual(TextDifferences.EQUAL, results_for_file.shd_diffs.diff_type)
        # TODO: Check TableDiff

    def test_case_a_fatal(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_FATAL, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)

    def test_bad_file_extension(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            },
            alt_filename='my_file.iQf'
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            },
            alt_filename='my_file.iQf'
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.iQf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_MISSING, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_MISSING, results_for_file.summary_result.simulation_status_case2)

    def test_expect_death_succeeds(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('EMSTestMathAndKill.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('EMSTestMathAndKill', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)

    def test_case_b_fatal(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_FATAL, results_for_file.summary_result.simulation_status_case2)

    def test_both_cases_fatal(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "fatal",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_FATAL, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_FATAL, results_for_file.summary_result.simulation_status_case2)

    def test_case_b_crash(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "crash",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_MISSING, results_for_file.summary_result.simulation_status_case2)

    def test_case_b_unknown(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "unknown",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_UNKNOWN, results_for_file.summary_result.simulation_status_case2)

    def test_small_diffs(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "smalldiffs",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have created a run directory for this file, put input files there, and left output files there
        file_results_dir = results_dir / 'my_file'
        self.assertTrue(file_results_dir.exists())
        self.assertTrue((file_results_dir / 'in.epw').exists())
        self.assertTrue((file_results_dir / 'in.idf').exists())
        self.assertTrue((file_results_dir / 'eplusout.eso').exists())
        self.assertTrue((file_results_dir / 'eplusout.end').exists())
        self.assertTrue((file_results_dir / 'eplusout.csv').exists())
        # check the diffs
        self.assertEqual('Small Diffs', results_for_file.eso_diffs.diff_type)
        self.assertEqual('Small Diffs', results_for_file.mtr_diffs.diff_type)
        self.assertEqual('Small Diffs', results_for_file.ssz_diffs.diff_type)
        self.assertEqual('Small Diffs', results_for_file.zsz_diffs.diff_type)

    def test_big_diffs(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "bigdiffs",
                    "txt_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have created a run directory for this file, put input files there, and left output files there
        file_results_dir = results_dir / 'my_file'
        self.assertTrue(file_results_dir.exists())
        self.assertTrue((file_results_dir / 'in.epw').exists())
        self.assertTrue((file_results_dir / 'in.idf').exists())
        self.assertTrue((file_results_dir / 'eplusout.eso').exists())
        self.assertTrue((file_results_dir / 'eplusout.end').exists())
        self.assertTrue((file_results_dir / 'eplusout.csv').exists())
        # check the diffs
        self.assertEqual('Big Diffs', results_for_file.eso_diffs.diff_type)
        self.assertEqual('Big Diffs', results_for_file.mtr_diffs.diff_type)
        self.assertEqual('Big Diffs', results_for_file.ssz_diffs.diff_type)
        self.assertEqual('Big Diffs', results_for_file.zsz_diffs.diff_type)

    def test_text_diffs(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base",
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "diffs"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # check the diffs
        self.assertEqual(TextDifferences.DIFFS, results_for_file.aud_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.bnd_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.dl_in_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.dl_out_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.dxf_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.eio_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.err_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.mdd_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.mtd_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.rdd_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.shd_diffs.diff_type)
        self.assertEqual(TextDifferences.DIFFS, results_for_file.idf_diffs.diff_type)

    def test_tiny_numeric_text_diffs(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "base",
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "txt_results": "small_numeric_text"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # check the diffs
        self.assertEqual(TextDifferences.EQUAL, results_for_file.eio_diffs.diff_type)

    def test_base_case_but_multi_process(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather'), TestEntry('my_macro_file.imf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=2,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(2, len(diff_results.entries_by_file))
        # these next blocks are pragma -ed from coverage because we don't know which one will get hit
        if diff_results.entries_by_file[0].basename == 'my_file':  # pragma: no cover
            results_for_file = diff_results.entries_by_file[0]
        else:  # if diff_results.entries_by_file[1].basename == 'my_file':  # pragma: no cover
            results_for_file = diff_results.entries_by_file[1]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have created a run directory for this file, put input files there, and left output files there
        file_results_dir = results_dir / 'my_file'
        self.assertTrue(file_results_dir.exists())
        self.assertTrue((file_results_dir / 'in.epw').exists())
        self.assertTrue((file_results_dir / 'in.idf').exists())
        self.assertTrue((file_results_dir / 'eplusout.eso').exists())
        self.assertTrue((file_results_dir / 'eplusout.end').exists())
        self.assertTrue((file_results_dir / 'eplusout.csv').exists())

    def test_window5_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "Window5DataFile.dat"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "Window5DataFile.dat"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put Window5 dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'datasets' / 'Window5DataFile.dat').exists())

    def test_tdv_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(  # noqa: W605
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": r"DataSets\TDV"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(  # noqa: W605
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": r"DataSets\TDV"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put TDV dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'datasets' / 'TDV' / 'dummy.txt').exists())

    def test_hybrid_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "HybridZoneModel_TemperatureData.csv"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "HybridZoneModel_TemperatureData.csv"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put TDV dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'HybridZoneModel_TemperatureData.csv').exists())

    def test_solar_shading_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "SolarShadingTest_Shading_Data.csv"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "SolarShadingTest_Shading_Data.csv"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put TDV dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'SolarShadingTest_Shading_Data.csv').exists())

    def test_local_env_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "LocalEnvData.csv"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "LocalEnvData.csv"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put TDV dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'LocalEnvData.csv').exists())

    def test_macro_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ""
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ""
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_macro_file.imf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_macro_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put Macro files in the run directory
        file_results_dir = results_dir / 'my_macro_file'
        self.assertTrue((file_results_dir / 'extra.imf').exists())

    def test_lookup_table_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "LookupTable.csv"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": "LookupTable.csv"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put the CSV LookupTable files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'LookupTable.csv').exists())

    def test_hybrid_model_file_gets_dependencies(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ""
                }
            },
            alt_filename='HybridModelBlah.idf'
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ""
                }
            },
            alt_filename='HybridModelBlah.idf'
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('HybridModelBlah.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('HybridModelBlah', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put the CSV LookupTable files in the run directory
        file_results_dir = results_dir / 'HybridModelBlah'
        self.assertTrue((file_results_dir / 'HybridModel_Measurements_with_HVAC.csv').exists())
        self.assertTrue((file_results_dir / 'HybridModel_Measurements_no_HVAC.csv').exists())

    def test_missing_weather_still_gets_epw(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ""
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ""
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather_DOES_NOT_EXIST')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put an epw files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'in.epw').exists())

    def test_report_variable_dictionary_gets_scrubbed(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": 'report variable dictionary'
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": 'report variable dictionary'
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put TDV dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'in.idf').exists())
        with (file_results_dir / 'in.idf').open() as f_idf:
            body = f_idf.read()
            self.assertNotIn('report variable dictionary', body)

    def test_parametric_is_signalled(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": 'Parametric:'
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": 'Parametric:'
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertTrue((results_dir / 'test_results.json').exists())
        self.assertTrue((results_dir / 'run_times.csv').exists())
        # it should have put TDV dataset files in the run directory
        file_results_dir = results_dir / 'my_file'
        self.assertTrue((file_results_dir / 'in.idf').exists())
        self.assertTrue((file_results_dir / 'in-02.idf').exists())

    def test_external_interface_is_executed(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": 'ExternalInterface:'
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": 'ExternalInterface:'
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have been skipped in both cases, so missing
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)

    def test_ashrae_205_files_execute(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ':ASHRAE205'
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base",
                    "extra_data": ':ASHRAE205'
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod,
            force_output_sql=ForceOutputSQL.SIMPLE,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.NONE
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have been skipped in both cases, so missing
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        results_dir = diff_results.results_dir_a
        file_results_dir = results_dir / 'my_file'
        cbor_files_to_check = [
            'CoolSys1-Chiller.RS0001.a205.cbor',
            'A205ExampleChiller.RS0001.a205.cbor',
            'CoolSys1-Chiller-Detailed.RS0001.a205.cbor',
        ]
        for cbor_file_to_check in cbor_files_to_check:
            self.assertTrue((file_results_dir / cbor_file_to_check).exists())

    def test_both_success_no_diffs_dd_only(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.DD,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertIn('DDOnly', str(results_dir))

    def test_epjson_file(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base"
                }
            },
            alt_filename='my_file.epJSON'
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base"
                }
            },
            alt_filename='my_file.epJSON'
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.epJSON', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.DD,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertIn('DDOnly', str(results_dir))

    def test_both_success_no_diffs_annual(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.ANNUAL,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file', results_for_file.basename)
        # it should have succeeded in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_SUCCESS, results_for_file.summary_result.simulation_status_case2)
        # it should have created a test directory and dropped the summaries there
        results_dir = diff_results.results_dir_a
        self.assertIn('Annual', str(results_dir))

    def test_file_does_not_exist(self):
        base = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_base_build_dir,
            self.temp_base_source_dir,
            {
                "config": {
                    "run_time_string": "01hr 20min  0.17sec",
                    "num_warnings": 1,
                    "num_severe": 0,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        base.set_build_directory(self.temp_base_build_dir)

        mod = CMakeCacheMakeFileBuildDirectory()
        self.establish_build_folder(
            self.temp_mod_build_dir,
            self.temp_mod_source_dir,
            {
                "config": {
                    "run_time_string": "00hr 10min  0.17sec",
                    "num_warnings": 2,
                    "num_severe": 1,
                    "end_state": "success",
                    "eso_results": "base"
                }
            }
        )
        mod.set_build_directory(self.temp_mod_build_dir)

        entries = [TestEntry('my_file_DOES_NOT_EXIST.idf', 'my_weather')]
        config = TestRunConfiguration(
            force_run_type=ForceRunType.NONE,
            single_test_run=False,
            num_threads=1,
            report_freq=ReportingFreq.HOURLY,
            build_a=base,
            build_b=mod
        )
        r = SuiteRunner(config, entries, mute=True)
        r.run_test_suite()
        diff_results = r.completed_structure
        # there should be 1 file result
        self.assertEqual(1, len(diff_results.entries_by_file))
        results_for_file = diff_results.entries_by_file[0]
        # it should be named according to what we listed above
        self.assertEqual('my_file_DOES_NOT_EXIST', results_for_file.basename)
        # it should have failed in both base and mod cases
        self.assertEqual(EndErrSummary.STATUS_MISSING, results_for_file.summary_result.simulation_status_case1)
        self.assertEqual(EndErrSummary.STATUS_MISSING, results_for_file.summary_result.simulation_status_case2)

    def test_eio_with_version(self):
        # tests that the Version, XX.N line is ignored in the EIO
        base_eio = self.temp_mod_source_dir / 'base.eio'
        mod_eio = self.temp_mod_source_dir / 'mod.eio'
        with open(base_eio, 'w') as f:
            f.write(' ! <Version>, Version ID\nVersion, 9.6\n')
        with open(mod_eio, 'w') as f:
            f.write(' ! <Version>, Version ID\nVersion, 22.1\n')
        diff_file = self.temp_mod_source_dir / 'diff.eio'
        self.assertEqual(TextDifferences.EQUAL, SuiteRunner.diff_text_files(base_eio, mod_eio, diff_file))

    def test_eio_diff_with_utf8(self):
        base_eio = self.resources / 'eplusout_with_utf8_base.eio'
        mod_eio = self.resources / 'eplusout_with_utf8_mod.eio'
        diff_file = self.temp_base_build_dir / 'eio.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_text_files(base_eio, mod_eio, diff_file))

    def test_err_diff_equal_with_ignored_differences(self):
        base_err = self.resources / 'eplusout_base.err'
        mod_err = self.resources / 'eplusout_mod.err'
        diff_file = self.temp_base_build_dir / 'err.diff'
        self.assertEqual(TextDifferences.EQUAL, SuiteRunner.diff_text_files(base_err, mod_err, diff_file))

    def test_perf_log_equal_with_ignored_differences(self):
        base_perf_log = self.resources / 'eplusout_perflog_base.csv'
        mod_perf_log = self.resources / 'eplusout_perflog_same_except_times.csv'
        diff_file = self.temp_base_build_dir / 'perf_log.diff'
        self.assertEqual(TextDifferences.EQUAL, SuiteRunner.diff_perf_log(base_perf_log, mod_perf_log, diff_file))

    def test_perf_log_diffs(self):
        base_perf_log = self.resources / 'eplusout_perflog_base.csv'
        mod_perf_log = self.resources / 'eplusout_perflog_mod.csv'
        diff_file = self.temp_base_build_dir / 'perf_log.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_perf_log(base_perf_log, mod_perf_log, diff_file))

    def test_audit_diff_equal_with_ignored_differences(self):
        base_audit = self.resources / 'eplusout_base.audit'
        mod_audit = self.resources / 'eplusout_mod.audit'
        diff_file = self.temp_base_build_dir / 'err.audit'
        self.assertEqual(TextDifferences.EQUAL, SuiteRunner.diff_text_files(base_audit, mod_audit, diff_file))

    def test_glhe_diff(self):
        base_glhe = self.resources / 'eplusout_base.glhe'
        # case 1 they are equal
        mod_glhe = self.resources / 'eplusout_base.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.1.diff'
        self.assertEqual(TextDifferences.EQUAL, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))
        # case 2, they may be equal, but the names are different
        mod_glhe = self.resources / 'eplusout_mod_mismatch_object_names.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.2.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))
        # case 3, there are different numbers of GLHEs, don't compare
        mod_glhe = self.resources / 'eplusout_mod_mismatch_object_count.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.3.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))
        # case 4, different values
        mod_glhe = self.resources / 'eplusout_mod_bad_values.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.4.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))
        # case 5, same values but different order
        mod_glhe = self.resources / 'eplusout_mod_text_diff_but_json_equal.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.5.diff'
        self.assertEqual(TextDifferences.EQUAL, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))
        # case 6, mismatched g function counts
        mod_glhe = self.resources / 'eplusout_mod_mismatched_counts.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.6.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))
        # case 7, bad key
        mod_glhe = self.resources / 'eplusout_mod_bad_key.glhe'
        diff_file = self.temp_base_build_dir / 'glhe.7.diff'
        self.assertEqual(TextDifferences.DIFFS, SuiteRunner.diff_glhe_files(base_glhe, mod_glhe, diff_file))

    def test_json_time_series(self):
        # only hourly for now
        base_json = self.resources / 'eplusout_hourly_base.json'
        # case 1 they are equal
        mod_json = self.resources / 'eplusout_hourly_base.json'
        diff_file = self.temp_base_build_dir / 'json.1.diff'
        self.assertEqual(0, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 2 bad key causes diffs
        mod_json = self.resources / 'eplusout_hourly_mod_bad_key.json'
        diff_file = self.temp_base_build_dir / 'json.2.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 3, same values but different order
        mod_json = self.resources / 'eplusout_hourly_mod_text_diff_but_json_equal.json'
        diff_file = self.temp_base_build_dir / 'json.3.diff'
        self.assertEqual(0, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 4, a small diff
        mod_json = self.resources / 'eplusout_hourly_mod_small_diff.json'
        diff_file = self.temp_base_build_dir / 'json.4.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[3])
        # case 5, a small diff
        mod_json = self.resources / 'eplusout_hourly_mod_big_diff.json'
        diff_file = self.temp_base_build_dir / 'json.5.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 6, column name mismatch
        mod_json = self.resources / 'eplusout_hourly_mod_col_mismatch.json'
        diff_file = self.temp_base_build_dir / 'json.6.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 7, report frequency mismatch
        mod_json = self.resources / 'eplusout_hourly_mod_freq_mismatch.json'
        diff_file = self.temp_base_build_dir / 'json.7.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 8, row count mismatch
        mod_json = self.resources / 'eplusout_hourly_mod_row_count_mismatch.json'
        diff_file = self.temp_base_build_dir / 'json.8.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])
        # case 9, timestamp mismatch
        mod_json = self.resources / 'eplusout_hourly_mod_timestamp_mismatch.json'
        diff_file = self.temp_base_build_dir / 'json.9.diff'
        self.assertEqual(1, SuiteRunner.diff_json_time_series(base_json, mod_json, diff_file)[2])

    def test_content_reader(self):
        file_path_to_read = self.resources / 'BadUTF8Marker.idf'
        # this should simply pass without throwing an exception
        SuiteRunner.read_file_content(file_path_to_read)


class TestSQLiteForce(unittest.TestCase):

    def test_not_present(self):
        idf_text = ""
        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.NOFORCE)
        self.assertEqual("""
  Output:SQLite,
    SimpleAndTabular;        !- Option Type
""", mod_text)

        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.JtoKWH)
        self.assertEqual("""
  Output:SQLite,
    SimpleAndTabular,        !- Option Type
    JtoKWH;        !- Unit Conversion
""", mod_text)

    def test_already_there_no_unit_conv(self):
        idf_text = """

  Zone,
    Zone 1;

  Output:SqliTe,SiMPle;
"""

        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.NOFORCE)
        self.assertEqual("""

  Zone,
    Zone 1;

  Output:SQLite,
    SimpleAndTabular;

""", mod_text)

        # Force the UnitConv
        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.JtoGJ)
        self.assertEqual("""

  Zone,
    Zone 1;

  Output:SQLite,
    SimpleAndTabular,        !- Option Type
    JtoGJ;        !- Unit Conversion

""", mod_text)

    def test_already_there_with_unit_conv(self):
        idf_text = """

  Zone,
    Zone 1;

  Output:Sqlite,Simple,JtoGJ;
"""

        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.NOFORCE)
        self.assertEqual("""

  Zone,
    Zone 1;

  Output:SQLite,
    SimpleAndTabular,JtoGJ;

""", mod_text)

        # Force the UnitConv
        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.InchPound)
        self.assertEqual("""

  Zone,
    Zone 1;

  Output:SQLite,
    SimpleAndTabular,        !- Option Type
    InchPound;        !- Unit Conversion

""", mod_text)

    def test_not_present_epjson(self):
        idf_text = "{}"
        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.NOFORCE,
            is_ep_json=True
        )

        expected_data = {'Output:SQLite': {'Output:SQLite 1': {'option_type': 'SimpleAndTabular'}}}
        self.assertEqual(json.dumps(expected_data, indent=4), mod_text)

    def test_present_epjson(self):
        ori_data = {'Output:SQLite': {'Output:SQLite 4': {'option_type': 'Simple', 'unit_conversion': 'JtoKWH'}}}
        idf_text = json.dumps(ori_data)

        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.NOFORCE,
            is_ep_json=True
        )

        expected_data = {
            'Output:SQLite': {'Output:SQLite 4': {'option_type': 'SimpleAndTabular', 'unit_conversion': 'JtoKWH'}}}
        self.assertEqual(json.dumps(expected_data, indent=4), mod_text)

        mod_text = SuiteRunner.add_or_modify_output_sqlite(
            idf_text=idf_text,
            force_output_sql=ForceOutputSQL.SIMPLEANDTABULAR,
            force_output_sql_unitconv=ForceOutputSQLUnitConversion.InchPound,
            is_ep_json=True
        )

        expected_data = {
            'Output:SQLite': {'Output:SQLite 4': {'option_type': 'SimpleAndTabular', 'unit_conversion': 'InchPound'}}}
        self.assertEqual(json.dumps(expected_data, indent=4), mod_text)

    def test_modify_sqlite_with_bad_inputs(self):
        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            SuiteRunner.add_or_modify_output_sqlite("", "BLAH", ForceOutputSQLUnitConversion.NOFORCE)
        with self.assertRaises(ValueError):
            # noinspection PyTypeChecker
            SuiteRunner.add_or_modify_output_sqlite("", ForceOutputSQL.NOFORCE, "BLAH")
