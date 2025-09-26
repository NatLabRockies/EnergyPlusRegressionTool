#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import argparse
from datetime import datetime
import json
from pathlib import Path
from platform import system
import shutil
import sys
from multiprocessing import Pool
from typing import Callable
from difflib import unified_diff  # python's own diff library


from energyplus_regressions.builds.base import BuildTree, BaseBuildDirectoryStructure
from energyplus_regressions.diffs import math_diff, table_diff, thresh_dict as td
from energyplus_regressions.energyplus import ExecutionArguments, execute_energyplus
from energyplus_regressions.structures import (
    ForceRunType,
    TextDifferences,
    EndErrSummary,
    MathDifferences,
    TableDifferences,
    CompletedStructure,
    ReportingFreq,
    ForceOutputSQL,
    ForceOutputSQLUnitConversion,
    TestEntry
)
from energyplus_regressions.results import ResultsManager

if getattr(sys, 'frozen', False):  # pragma: no cover -- not covering frozen apps in unit tests
    frozen = True
else:
    frozen = False

# get the current file path for convenience
script_dir = Path(__file__).resolve().parent

RunArgs = tuple[TestEntry, BuildTree, BuildTree, str, Path]


class TestRunConfiguration:
    __test__ = False  # so that PyTest doesn't try to run this as a class fixture

    def __init__(self, force_run_type: str, num_threads: int, report_freq: str,
                 build_a: BaseBuildDirectoryStructure, build_b: BaseBuildDirectoryStructure,
                 single_test_run: bool = False, force_output_sql: ForceOutputSQL = ForceOutputSQL.NOFORCE,
                 force_output_sql_unitconv: ForceOutputSQLUnitConversion = ForceOutputSQLUnitConversion.NOFORCE):
        self.force_run_type = force_run_type
        self.TestOneFile = single_test_run
        self.num_threads = num_threads
        self.buildA = build_a
        self.buildB = build_b
        self.report_freq = report_freq
        self.force_output_sql = ForceOutputSQL(force_output_sql)
        self.force_output_sql_unitconv = ForceOutputSQLUnitConversion(force_output_sql_unitconv)


class TestCaseCompleted:
    __test__ = False  # so that PyTest doesn't try to run this as a class fixture

    def __init__(self, run_directory: str, case_name: str, run_status, error_msg_reported_already, extra_message=""):
        self.run_directory = run_directory
        self.case_name = case_name
        self.run_success = run_status
        self.muffle_err_msg = error_msg_reported_already
        self.extra_message = extra_message


# the actual main test suite run class
class SuiteRunner:

    def __init__(self, run_config: TestRunConfiguration, these_entries: list[TestEntry], mute=False):

        # initialize the master mute button -- this is overridden by registering callbacks
        self.mute = mute

        # initialize callbacks
        self.print_callback = None
        self.starting_callback = None
        self.case_completed_callback = None
        self.simulations_complete_callback = None
        self.diff_completed_callback = None
        self.all_done_callback = None
        self.cancel_callback = None

        # set a few things
        self.id_like_to_stop_now = False
        self.completed_structure = None

        # User configuration; read from the run_configuration
        self.force_run_type = run_config.force_run_type
        self.TestOneFile = run_config.TestOneFile
        self.number_of_threads = int(run_config.num_threads)
        self.min_reporting_freq = run_config.report_freq
        self.force_output_sql = run_config.force_output_sql
        self.force_output_sql_unitconv = run_config.force_output_sql_unitconv

        # File list brought in separately
        self.entries = these_entries

        # Main test configuration here
        self.build_tree_a: BuildTree = run_config.buildA.get_build_tree()
        self.build_tree_b: BuildTree = run_config.buildB.get_build_tree()

        # Settings/paths defined relative to this script
        # self.path_to_file_list = os.path.join(script_dir, "files_to_run.txt")
        self.thresh_dict_file = script_dir / 'diffs' / "math_diff.config"
        # self.math_diff_executable = os.path.join(script_dir, "math_diff.py")
        # self.table_diff_executable = os.path.join(script_dir, "table_diff.py")

        # Settings/paths defined relative to the buildA/buildB test directories
        # the tests directory will be different based on forceRunType
        if self.force_run_type == ForceRunType.ANNUAL:
            self.test_output_dir = "Tests-Annual"
        elif self.force_run_type == ForceRunType.DD:
            self.test_output_dir = "Tests-DDOnly"
        elif self.force_run_type == ForceRunType.NONE:
            self.test_output_dir = "Tests"
        i = datetime.now()
        self.test_output_dir += i.strftime('_%Y%m%d_%H%M%S')

        # For files that don't have a specified weather file, use Chicago
        self.default_weather_filename = "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"

    def run_test_suite(self) -> None:

        # reset this flag
        self.id_like_to_stop_now = False

        # do some preparation
        self.prepare_dir_structure(self.build_tree_a, self.build_tree_b, self.test_output_dir)

        if self.id_like_to_stop_now:  # pragma: no cover
            self.my_cancelled()
            return

        start_time = datetime.now()
        self.my_starting(len(self.entries))

        # run the energyplus script
        self.run_build(self.build_tree_a)
        if self.id_like_to_stop_now:  # pragma: no cover
            self.my_cancelled()
            return
        self.run_build(self.build_tree_b)
        if self.id_like_to_stop_now:  # pragma: no cover
            self.my_cancelled()
            return
        self.my_simulations_complete()

        self.diff_logs_for_build(start_time)

        try:
            self.my_print('Writing runtime summary file')
            csv_file_path = self.build_tree_a.build_dir / self.test_output_dir / 'run_times.csv'
            self.completed_structure.to_runtime_summary(csv_file_path)
            self.my_print('Runtime summary written successfully')
        except Exception as this_exception:  # pragma: no cover
            self.my_print('Could not write runtime summary file: ' + str(this_exception))

        try:
            self.my_print('Writing simulation results summary file')
            json_file_path = self.build_tree_a.build_dir / self.test_output_dir / 'test_results.json'
            self.completed_structure.to_json_summary(json_file_path)
            self.my_print('Results summary written successfully')
        except Exception as this_exception:  # pragma: no cover
            self.my_print('Could not write results summary file: ' + str(this_exception))

        self.my_print("Test suite complete for directories:")
        self.my_print(" --build-1--> %s" % self.build_tree_a.build_dir)
        self.my_print(" --build-2--> %s" % self.build_tree_b.build_dir)
        self.my_print("Test suite complete")

        ResultsManager(mute=True).build_summary_content(self.completed_structure)
        self.my_all_done(self.completed_structure)
        return

    def prepare_dir_structure(self, b_a: BuildTree, b_b: BuildTree, d_test: str):
        # make tests directory as needed
        if b_a:
            d = b_a.build_dir / d_test
            if not d.exists():
                d.mkdir()
        if b_b:
            d = b_b.build_dir / d_test
            if not d.exists():
                d.mkdir()
        self.my_print('Created test directories at <build-dir>/%s' % d_test)

    @staticmethod
    def read_file_content(file_path: Path):
        with file_path.open(encoding='utf-8', errors='ignore') as f_idf:
            idf_text = f_idf.read()
        return idf_text

    @staticmethod
    def add_or_modify_output_sqlite(idf_text, force_output_sql: ForceOutputSQL,
                                    force_output_sql_unitconv: ForceOutputSQLUnitConversion,
                                    is_ep_json: bool = False):
        """Will add or modify the Output:SQLite object based on the provided enums that corresponds to the 'Option'"""
        # Ensure we deal with the enum
        if not isinstance(force_output_sql, ForceOutputSQL):
            raise ValueError("Expected an Enum ForceOutputSQL, not {}".format(force_output_sql))

        if not isinstance(force_output_sql_unitconv, ForceOutputSQLUnitConversion):
            raise ValueError("Expected an Enum ForceOutputSQLUnitConversion, not "
                             "{}".format(force_output_sql_unitconv))

        # special ugly case for handling unit testing -- note that the unit testing here is based around a "dummy"
        # energyplus which reads in a small JSON configuration blob, even though it thinks it is an IDF.  This confuses
        # this function, so I'll put in a small trick to just let the code pass through
        if idf_text.startswith('{"config"'):
            return idf_text

        if is_ep_json:
            data = json.loads(idf_text)
            if "Output:SQLite" in data and len(data["Output:SQLite"]) >= 1:
                sqlite_obj = data["Output:SQLite"][list(data["Output:SQLite"].keys())[0]]

            else:
                data["Output:SQLite"] = {"Output:SQLite 1": {}}
                sqlite_obj = data["Output:SQLite"]["Output:SQLite 1"]

            sqlite_obj['option_type'] = force_output_sql.value
            if force_output_sql_unitconv != ForceOutputSQLUnitConversion.NOFORCE:
                sqlite_obj['unit_conversion'] = force_output_sql_unitconv.value

            return json.dumps(data, indent=4)

        # IDF / IMF text manipulation
        has_sqlite_object = False
        for line in idf_text.splitlines():
            if 'output:sqlite' in line.split('!')[0].lower():
                has_sqlite_object = True
                break
        if has_sqlite_object:
            import re
            re_sqlite = re.compile(r'Output:SQlite\s*,(?P<Option>[^,;]*?)\s*(?P<TabularUnitConv>,[^,;]*?\s*)?;',
                                   re.IGNORECASE)
            if force_output_sql_unitconv == ForceOutputSQLUnitConversion.NOFORCE:
                idf_text = re_sqlite.sub(r'Output:SQLite,\n    {}\g<TabularUnitConv>;\n'.format(force_output_sql.value),
                                         idf_text)
            else:
                new_obj = '''Output:SQLite,
    {},        !- Option Type
    {};        !- Unit Conversion
'''.format(force_output_sql.value, force_output_sql_unitconv.value)

                idf_text = re_sqlite.sub(new_obj,
                                         idf_text)
        else:
            if force_output_sql_unitconv == ForceOutputSQLUnitConversion.NOFORCE:
                idf_text += '\n  Output:SQLite,\n    {};        !- Option Type\n'.format(force_output_sql.value)
            else:
                idf_text += '''
  Output:SQLite,
    {},        !- Option Type
    {};        !- Unit Conversion
'''.format(force_output_sql.value, force_output_sql_unitconv.value)

        return idf_text

    def run_build(self, build_tree: BuildTree):

        this_test_dir: str = self.test_output_dir
        local_run_type: str = self.force_run_type

        # Create a job list
        energy_plus_runs: list[ExecutionArguments] = []

        # loop over all entries
        for this_entry in self.entries:
            # get a few convenience, typed, variables
            build_dir: Path = build_tree.build_dir
            test_files_dir: Path = build_tree.test_files_dir
            base_name: str = this_entry.basename
            weather_dir: Path = build_tree.weather_dir

            # first remove the previous test directory for this file and rename it
            test_run_directory: Path = build_dir / this_test_dir / base_name
            if test_run_directory.exists():  # pragma: no cover - dir name is generated by local timestamp now
                shutil.rmtree(test_run_directory)
            test_run_directory.mkdir()

            # establish the absolute path to the idf or imf, and append .idf or .imf as necessary

            full_input_file_path: Path = test_files_dir / this_entry.name_relative_to_testfiles_dir

            parametric_file: bool = False
            if not full_input_file_path.exists():
                self.my_print(f"Input file does not exist: {full_input_file_path}")
                self.my_case_completed(TestCaseCompleted(this_test_dir, base_name, False, False))
                continue

            # copy macro files if it is an imf
            is_ep_json: bool = False
            if full_input_file_path.name.endswith('.idf'):
                ep_in_filename = "in.idf"
            elif full_input_file_path.name.endswith('.imf'):
                # noinspection PyUnusedLocal
                ep_in_filename = "in.imf"  # this is so weird, PyCharm really thinks this isn't used, but it is!
                # find the rest of the imf files and copy them into the test directory
                for full_file_name in test_files_dir.iterdir():
                    if full_file_name.name[-4:] == '.imf':
                        shutil.copy(full_file_name, build_dir / this_test_dir / base_name)
            elif full_input_file_path.name.endswith('.epJSON'):
                ep_in_filename = "in.epJSON"
                is_ep_json = True
            else:
                self.my_print(f"Invalid file extension, must be idf, imf, or epJSON: {full_input_file_path}")
                self.my_case_completed(TestCaseCompleted(this_test_dir, base_name, False, False))
                continue

            # copy the input file into the test directory, renaming to in.idf or in.imf
            shutil.copy(full_input_file_path, test_run_directory / ep_in_filename)

            # read in the entire text of the idf to do some special operations;
            # could put in one line, but the with block ensures the file handle is closed
            idf_text = SuiteRunner.read_file_content(test_run_directory / ep_in_filename)

            # if the file requires the window 5 data set file, bring it into the test run directory
            if 'Window5DataFile.dat' in idf_text:
                data_sets_dir = test_run_directory / 'datasets'
                data_sets_dir.mkdir()
                shutil.copy(build_tree.data_sets_dir / 'Window5DataFile.dat', test_run_directory / 'datasets')
                idf_text = idf_text.replace('..\\datasets\\Window5DataFile.dat', 'datasets/Window5DataFile.dat')

            # if the file requires the TDV data set file, bring it
            #  into the test run directory, right now I think it's broken
            if 'DataSets\\TDV' in idf_text or 'DataSets\\\\TDV' in idf_text:
                data_sets_dir = test_run_directory / 'datasets'
                tdv_dir = data_sets_dir / 'TDV'
                data_sets_dir.mkdir()
                tdv_dir.mkdir()
                original_tdv_dir = build_tree.data_sets_dir / 'TDV'
                for full_file_name in original_tdv_dir.iterdir():
                    if full_file_name.is_file():
                        shutil.copy(full_file_name, tdv_dir)
                from os import sep
                idf_text = idf_text.replace(
                    '..\\datasets\\TDV\\TDV_2008_kBtu_CTZ06.csv',
                    sep.join(['datasets', 'TDV', 'TDV_2008_kBtu_CTZ06.csv'])
                )

            if 'HybridModel' in base_name:
                shutil.copy(
                    build_tree.test_files_dir / 'HybridModel_Measurements_with_HVAC.csv',
                    test_run_directory / 'HybridModel_Measurements_with_HVAC.csv'
                )
                shutil.copy(
                    build_tree.test_files_dir / 'HybridModel_Measurements_no_HVAC.csv',
                    test_run_directory / 'HybridModel_Measurements_no_HVAC.csv'
                )

            # several checks that just bring a single file from the test files dir based on the filename as a keyword
            single_file_checks = [
                'HybridZoneModel_TemperatureData.csv',
                'LookupTable.csv',
                'SolarShadingTest_Shading_Data.csv',
                'LocalEnvData.csv',
                'SurfacePropGndSurfs.csv',
            ]
            for single_file_check in single_file_checks:
                if single_file_check in idf_text:
                    shutil.copy(
                        build_tree.test_files_dir / single_file_check,
                        test_run_directory / single_file_check
                    )

            if 'report variable dictionary' in idf_text:
                idf_text = idf_text.replace('report variable dictionary', '')

            if 'Parametric:' in idf_text:
                parametric_file = True

            # if the file requires the FMUs data set file, bring it
            #  into the test run directory, right now I think it's broken
            if 'ExternalInterface:' in idf_text:
                # self.my_print('Skipping an FMU based file as this is not set up to run yet')
                # continue
                new_datasets_dir = test_run_directory / 'datasets'
                new_fmu_dir = new_datasets_dir / 'FMUs'
                new_datasets_dir.mkdir()
                new_fmu_dir.mkdir()
                original_fmu_dir = build_tree.data_sets_dir / 'FMUs'
                for full_file_name in original_fmu_dir.iterdir():
                    if full_file_name.is_file():
                        shutil.copy(
                            full_file_name,
                            test_run_directory / 'datasets' / 'FMUs'
                        )
                idf_text = idf_text.replace('..\\datasets', 'datasets')

            if ':ASHRAE205' in idf_text:
                # need to copy in the cbor data files so that they can run
                supporting_205_files = [
                    'CoolSys1-Chiller.RS0001.a205.cbor',
                    'A205ExampleChiller.RS0001.a205.cbor',
                    'CoolSys1-Chiller-Detailed.RS0001.a205.cbor',
                    'residential-dx.RS0004.json',
                ]
                for cbor_file in supporting_205_files:
                    shutil.copy(
                        build_tree.test_files_dir / cbor_file,
                        test_run_directory / cbor_file
                    )

            # Add Output:SQLite if requested
            if self.force_output_sql != ForceOutputSQL.NOFORCE:
                idf_text = self.add_or_modify_output_sqlite(
                    idf_text=idf_text, force_output_sql=self.force_output_sql,
                    force_output_sql_unitconv=self.force_output_sql_unitconv,
                    is_ep_json=is_ep_json
                )

            # rewrite the idf with the (potentially) modified idf text
            new_idf_file = build_tree.build_dir / this_test_dir / base_name / ep_in_filename
            with new_idf_file.open('w', encoding='utf-8') as f_i:
                f_i.write("%s\n" % idf_text)

            rvi: Path = test_files_dir / (base_name + '.rvi')
            if rvi.exists():
                shutil.copy(rvi, build_tree.build_dir / this_test_dir / base_name / 'in.rvi')

            mvi: Path = test_files_dir / (base_name + '.mvi')
            if mvi.exists():
                shutil.copy(mvi, build_tree.build_dir / this_test_dir / base_name / 'in.mvi')

            # pick up the corresponding python plugin file, for now this is just the idf basename with .py extension
            py: Path = test_files_dir / (base_name + '.py')
            if py.exists():
                shutil.copy(py, build_dir / this_test_dir / base_name / (base_name + '.py'))

            epw_path: Path = weather_dir / self.default_weather_filename
            if this_entry.epw:
                epw_path = weather_dir / (this_entry.epw + '.epw')
                if not epw_path.exists():
                    self.my_print(
                        "For case %s, weather file did not exist at %s, using a default one!" % (
                            base_name, epw_path
                        )
                    )
                    epw_path = weather_dir / self.default_weather_filename

            energy_plus_runs.append(
                ExecutionArguments(
                    build_tree,
                    base_name,
                    test_run_directory,
                    local_run_type,
                    self.min_reporting_freq,
                    parametric_file,
                    str(epw_path)
                )
            )

        # So...on Windows, pyinstaller freezes the application, and then multiprocessing vomits on this.
        # If you are running this from code, say from a Pip install, it works fine.  It's merely the combination of
        # freezing _plus_ multiprocessing.  Apparently the tool needs to run multiprocessing.freeze_support(), which I
        # tried, but that wasn't sufficient.  There is also a hack you can do to override the multiprocessing.Process
        # class and add some extra stuff in there, but I could not figure out how to integrate that along with the
        # `apply_async` approach I am using.  Gross.  Once again, on Windows, this means it will partially not be
        # multithreaded.
        if self.number_of_threads == 1 or frozen and system() in ['Windows', 'Darwin']:  # pragma: no cover
            if self.number_of_threads > 1:
                self.my_print("Ignoring num_threads on frozen Windows/Mac instance, just running with one thread.")
            for run in energy_plus_runs:
                ep_return = self.ep_wrapper(run)
                self.ep_done(ep_return)
        else:  # for all other applications, run them in a multiprocessing pool
            p = Pool(self.number_of_threads)
            for run in energy_plus_runs:
                p.apply_async(self.ep_wrapper, (run,), callback=self.ep_done, error_callback=self.ep_done)
            p.close()
            p.join()

    def ep_wrapper(self, run_args):  # pragma: no cover -- this is being skipped by coverage?
        if self.id_like_to_stop_now:
            return ["", "Cancelled", False, False]
        return execute_energyplus(run_args)

    def ep_done(self, results):
        self.my_case_completed(TestCaseCompleted(*results))

    @staticmethod
    def both_files_exist(base_path_a: Path, base_path_b: Path, common_relative_path):
        if (base_path_a / common_relative_path).exists():
            if (base_path_b / common_relative_path).exists():
                return True
        return False

    @staticmethod
    def diff_perf_log(file_a: Path, file_b: Path, diff_file: Path):
        # will do a pretty simple CSV text token comparison, no numeric comparison, and omit some certain patterns
        tokens_to_skip = [1, 2, 27, 28, 30, 31]
        with file_a.open(encoding='utf-8') as f_txt_1:
            txt1 = f_txt_1.readlines()
        with file_b.open(encoding='utf-8') as f_txt_2:
            txt2 = f_txt_2.readlines()
        txt1_cleaned = []
        for line in txt1:
            tokens = line.split(',')
            for i in tokens_to_skip:
                if i < len(tokens):
                    tokens[i] = '***'
            txt1_cleaned.append(','.join(tokens))
        txt2_cleaned = []
        for line in txt2:
            tokens = line.split(',')
            for i in tokens_to_skip:
                if i < len(tokens):
                    tokens[i] = '***'
            txt2_cleaned.append(','.join(tokens))
        if txt1_cleaned == txt2_cleaned:
            return TextDifferences.EQUAL
        # if we aren't equal, compute the comparison and write to the output file, return that diffs occurred
        comparison = unified_diff(txt1_cleaned, txt2_cleaned)
        with diff_file.open('w', encoding='utf-8') as out_file:
            out_lines = list(comparison)
            for out_line in out_lines:
                out_file.write(out_line)
        return TextDifferences.DIFFS

    @staticmethod
    def is_float_ish(string: str) -> bool:
        try:
            float(string)
            return True
        except ValueError:
            return False

    @staticmethod
    def diff_text_files(file_a: Path, file_b: Path, diff_file: Path):
        # read the contents of the two files into a list, could read it into text first
        with file_a.open(encoding='utf-8') as f_txt_1:
            txt1 = f_txt_1.readlines()
        with file_b.open(encoding='utf-8') as f_txt_2:
            txt2 = f_txt_2.readlines()
        # remove any lines that have some specific listed strings in them
        txt1_cleaned = []
        skip_strings = [
            "Program Version,EnergyPlus",
            "Version,",
            "EnergyPlus Completed",
            "EnergyPlus Terminated",
            "DElight input generated",
            "(idf)=",
            "(user input)=",
            "(input file)=",
            "(IDF Directory)=",
            "(Current Working Directory)=",
            "(Current Working Directory)\"=",
            "ReadVars Run Time",
            "EnergyPlus Program Version",
            "PythonPlugin: Class",
            "ExpandObjects Finished. Time:",
            "EnergyPlus, Version",
            "EnergyPlus Run Time=",
            "ParametricPreprocessor Finished. Time:",
            "ExpandObjects Finished with Error(s). Time:",
            "Elapsed time: ",
        ]
        for line in txt1:
            if any([x in line for x in skip_strings]):
                txt1_cleaned.append('-line skipped-')
            else:
                txt1_cleaned.append(line)
        txt2_cleaned = []
        for line in txt2:
            if any([x in line for x in skip_strings]):
                txt2_cleaned.append('-line skipped-')
            else:
                txt2_cleaned.append(line)
        if txt1_cleaned == txt2_cleaned:
            return TextDifferences.EQUAL

        # CSV-style files, try parsing each line by token, comparing numerics, and if the lines are *effectively* the
        # same, don't include it in the diff.  This will help avoid something like 0.001 to 1.0E-03 causing diffs
        if file_a.name.endswith('.eio'):
            txt1_numeric_checked = []
            txt2_numeric_checked = []
            for c1, c2 in zip(txt1_cleaned, txt2_cleaned):
                tokens_1 = [x.strip() for x in c1.split(',')]
                tokens_2 = [x.strip() for x in c2.split(',')]
                if len(tokens_1) != len(tokens_2):  # if we have a different length, then immediately something changed
                    txt1_numeric_checked.append(c1)
                    txt2_numeric_checked.append(c2)
                else:  # otherwise let's check things by token and see what happens
                    # initially these flags are false, and will remain that way if we only find alphas and no diffs
                    numeric_tokens_found = False
                    actual_diffs_found = False
                    for t1, t2 in zip(tokens_1, tokens_2):
                        if SuiteRunner.is_float_ish(t1) and SuiteRunner.is_float_ish(t2):
                            numeric_tokens_found = True
                            if abs(float(t1) - float(t2)) > 0.000000000001:
                                actual_diffs_found = True  # we found numeric diffs that were meaningful!
                                break
                        elif t1 != t2:
                            actual_diffs_found = True  # we found non-numeric diffs, which are of course, meaningful
                            break
                    if numeric_tokens_found:
                        if actual_diffs_found:  # if the line had numeric diffs that were meaningful, write the lines
                            txt1_numeric_checked.append(c1)
                            txt2_numeric_checked.append(c2)
                        else:  # but if the line had numeric tokens that were not meaningful, and no other diffs, ignore
                            txt1_numeric_checked.append('-different, but equivalent numeric tokens found in line-\n')
                            txt2_numeric_checked.append('-different, but equivalent numeric tokens found in line-\n')
                    else:
                        # if there were no numeric tokens, just write the line regardless of whether it has diffs or
                        # not, so that we can see as much context as possible in the diff report
                        txt1_numeric_checked.append(c1)
                        txt2_numeric_checked.append(c2)
        else:
            txt1_numeric_checked = txt1_cleaned
            txt2_numeric_checked = txt2_cleaned
        if all([x == y for x, y in zip(txt1_numeric_checked, txt2_numeric_checked)]):
            return TextDifferences.EQUAL

        # if we aren't equal, compute the comparison and write to the output file, return that diffs occurred
        comparison = unified_diff(txt1_numeric_checked, txt2_numeric_checked)
        with diff_file.open('w', encoding='utf-8') as out_file:
            out_lines = list(comparison)
            for out_line in out_lines:
                out_file.write(out_line)
        return TextDifferences.DIFFS

    @staticmethod
    def diff_glhe_files(file_a: Path, file_b: Path, diff_file: Path):
        with file_a.open(encoding='utf-8') as f_txt_1:
            txt1 = f_txt_1.read()
        with file_b.open(encoding='utf-8') as f_txt_2:
            txt2 = f_txt_2.read()
        # return early if the files match
        if txt1 == txt2:
            return TextDifferences.EQUAL
        # if they don't match as a string, they could still match in terms of values, need to parse into objects
        json_1 = json.loads(txt1)
        json_2 = json.loads(txt2)
        if json_1 == json_2:
            return TextDifferences.EQUAL
        # ok, looks like there are actually diffs, time to parse through them
        # first, the highest level should be a dict with equal keys
        diffs = []
        names_ok = True
        if not len(json_1.keys()) == len(json_2.keys()):
            diffs.append("GLHE Object count doesn't match")
            names_ok = False
        elif not sorted(json_1.keys()) == sorted(json_2.keys()):
            diffs.append("GLHE Object names don't match")
            names_ok = False
        if names_ok:
            # then it's OK to continue diff-ing
            for glhe_name in json_1.keys():
                glhe_in_file_1 = json_1[glhe_name]
                glhe_in_file_2 = json_2[glhe_name]
                try:
                    pd1 = glhe_in_file_1['Phys Data']
                    pd2 = glhe_in_file_2['Phys Data']
                    keys_to_search = [
                        "BH Diameter",
                        "BH Length",
                        "BH Top Depth",
                        "Flow Rate",
                        "Grout k",
                        "Grout rhoCp",
                        "Max Simulation Years",
                        "Pipe Diameter",
                        "Pipe Thickness",
                        "Pipe k",
                        "Pipe rhoCP",
                        "Soil k",
                        "Soil rhoCp",
                        "U-tube Dist"
                    ]
                    for key in keys_to_search:
                        if (key in pd1 and key not in pd2) or (key not in pd1 and key in pd2):
                            diffs.append("Phys Data key differences for GLHE object named \"%s\"" % glhe_name)
                        elif not pd1[key] == pd2[key]:
                            diffs.append("Different Phys Data values in GLHE object named \"%s\"; field: \"%s\"" % (
                                glhe_name, key
                            ))
                    boreholes_1 = pd1['BH Data']
                    boreholes_2 = pd2['BH Data']
                    for borehole_name in boreholes_1.keys():
                        bh_in_file_1 = boreholes_1[borehole_name]
                        bh_in_file_2 = boreholes_2[borehole_name]
                        if not bh_in_file_1['X-Location'] == bh_in_file_2['X-Location']:
                            diffs.append("Borehole X location difference for GLHE \"%s\", borehole \"%s\"" % (
                                glhe_name, borehole_name
                            ))
                        if not bh_in_file_1['Y-Location'] == bh_in_file_2['Y-Location']:
                            diffs.append("Borehole Y location difference for GLHE \"%s\", borehole \"%s\"" % (
                                glhe_name, borehole_name
                            ))
                    response_factors_1 = glhe_in_file_1['Response Factors']
                    response_factors_2 = glhe_in_file_2['Response Factors']
                    g_function_1 = response_factors_1['GFNC']
                    g_function_2 = response_factors_2['GFNC']
                    ln_t_ts_1 = response_factors_1['LNTTS']
                    ln_t_ts_2 = response_factors_2['LNTTS']
                    time_1 = response_factors_1['time']
                    time_2 = response_factors_2['time']
                    counts_match = True
                    if not len(g_function_1) == len(g_function_2):
                        diffs.append("Mismatched GFNC count for GLHE \"%s\"" % glhe_name)
                        counts_match = False
                    if not len(ln_t_ts_1) == len(ln_t_ts_2):
                        diffs.append("Mismatched LNTTS count for GLHE \"%s\"" % glhe_name)
                        counts_match = False
                    if not len(time_1) == len(time_2):
                        diffs.append("Mismatched TIME count for GLHE \"%s\"" % glhe_name)
                        counts_match = False
                    if counts_match:
                        for i in range(len(g_function_1)):
                            if not g_function_1[i] == g_function_2[i]:
                                diffs.append("GFNC value diff for GLHE \"%s\"; index \"%s\"" % (glhe_name, i))
                            if not ln_t_ts_1[i] == ln_t_ts_2[i]:
                                diffs.append("LNTTS value diff for GLHE \"%s\"; index \"%s\"" % (glhe_name, i))
                            if not time_1[i] == time_2[i]:
                                diffs.append("TIME value diff for GLHE \"%s\"; index \"%s\"" % (glhe_name, i))
                except KeyError:
                    diffs.append("Key error in GLHE object named \"%s\"; something doesn't match" % glhe_name)
        with diff_file.open('w', encoding='utf-8') as out_file:
            my_json_str = json.dumps({"diffs": diffs}, ensure_ascii=False)
            out_file.write(my_json_str)
        return TextDifferences.DIFFS

    @staticmethod
    def diff_json_time_series(file_a: Path, file_b: Path, diff_file: Path):  # eventually handle the threshold dict here
        resulting_diff_type = "All Equal"
        num_values_checked = 0
        num_big_diffs = 0
        num_small_diffs = 0
        with file_a.open(encoding='utf-8') as f_txt_1:
            txt1 = f_txt_1.read()
        with file_b.open(encoding='utf-8') as f_txt_2:
            txt2 = f_txt_2.read()
        # return early if the files match
        if txt1 == txt2:
            return resulting_diff_type, num_values_checked, num_big_diffs, num_small_diffs
        # if they don't match as a string, they could still match in terms of values, need to parse into objects
        json_1 = json.loads(txt1)
        json_2 = json.loads(txt2)
        if json_1 == json_2:
            return resulting_diff_type, num_values_checked, num_big_diffs, num_small_diffs
        # ok, looks like there are actually diffs, time to parse through them
        diffs = []
        resulting_diff_type = "All Equal"
        num_values_checked = 0
        num_big_diffs = 0
        num_small_diffs = 0
        try:
            columns_1 = json_1['Cols']
            columns_2 = json_2['Cols']
            report_freq_1 = json_1['ReportFrequency']
            report_freq_2 = json_2['ReportFrequency']
            rows_1 = json_1['Rows']
            rows_2 = json_2['Rows']
            time_stamps_1 = [list(row.keys())[0] for row in rows_1]
            time_stamps_2 = [list(row.keys())[0] for row in rows_2]
            ok_to_continue = True
            if not columns_1 == columns_2:
                diffs.append("Column mismatch in JSON time-series output, numeric data not checked")
                resulting_diff_type = "Big Diffs"
                num_values_checked = 1
                num_big_diffs = 1
                ok_to_continue = False
            elif not report_freq_1 == report_freq_2:
                diffs.append("Report frequency mismatch in JSON time-series output, numeric data not checked")
                resulting_diff_type = "Big Diffs"
                num_values_checked = 1
                num_big_diffs = 1
                ok_to_continue = False
            elif not len(rows_1) == len(rows_2):
                diffs.append("Row count mismatch in JSON time-series output, numeric data not checked")
                resulting_diff_type = "Big Diffs"
                num_values_checked = 1
                num_big_diffs = 1
                ok_to_continue = False
            elif not time_stamps_1 == time_stamps_2:
                diffs.append("Timestamp mismatch in JSON time-series output, numeric data not checked")
                resulting_diff_type = "Big Diffs"
                num_values_checked = 1
                num_big_diffs = 1
                ok_to_continue = False
            if ok_to_continue:
                num_rows = len(rows_1)
                for row_num in range(num_rows):
                    this_row_1 = rows_1[row_num]
                    this_row_2 = rows_2[row_num]
                    this_time_stamp = list(this_row_1.keys())[0]
                    this_row_data_1 = this_row_1[this_time_stamp]
                    this_row_data_2 = this_row_2[this_time_stamp]
                    num_values = len(this_row_data_1)
                    for col_num in range(num_values):
                        num_values_checked += 1
                        value_1 = this_row_data_1[col_num]
                        value_2 = this_row_data_2[col_num]
                        if not value_1 == value_2:
                            f_1 = float(value_1)
                            f_2 = float(value_2)
                            if abs(f_1 - f_2) > 0.00001:
                                resulting_diff_type = 'Big Diffs'
                                num_big_diffs += 1
                            else:
                                if 'Big' not in resulting_diff_type:
                                    resulting_diff_type = 'Small Diffs'
                                num_small_diffs += 1
        except KeyError:
            diffs.append("JSON key problem in JSON time-series output, numeric data not checked")
            resulting_diff_type = "Big Diffs"
            num_values_checked = 1
            num_big_diffs = 1
        with diff_file.open('w', encoding='utf-8') as out_file:
            my_json_str = json.dumps(
                {'diffs': diffs, 'num_big_diffs': num_big_diffs, 'num_small_diffs': num_small_diffs},
                ensure_ascii=False
            )
            out_file.write(my_json_str)
        return resulting_diff_type, num_values_checked, num_big_diffs, num_small_diffs

    @staticmethod
    def process_diffs_for_one_case(
            this_entry, build_tree_a: BuildTree, build_tree_b: BuildTree,
            test_output_dir, thresh_dict_file, ci_mode=False
    ) -> tuple[TestEntry, str]:

        if ci_mode:  # in "ci_mode" the build directory is actually the output directory of each file
            case_result_dir_1 = build_tree_a.build_dir
            case_result_dir_2 = build_tree_b.build_dir
        else:
            case_result_dir_1 = build_tree_a.build_dir / test_output_dir / this_entry.basename
            case_result_dir_2 = build_tree_b.build_dir / test_output_dir / this_entry.basename

        out_dir = case_result_dir_1

        # we aren't using math_diff and table_diffs summary csv files, so use blanks
        path_to_math_diff_log = ""
        path_to_table_diff_log = ""

        # process the end files first
        status_case1 = EndErrSummary.STATUS_MISSING
        status_case2 = EndErrSummary.STATUS_MISSING
        runtime_case1 = 0
        runtime_case2 = 0
        end_path = case_result_dir_1 / 'eplusout.end'
        if end_path.exists():
            [status_case1, runtime_case1] = SuiteRunner.process_end_file(end_path)
        end_path = case_result_dir_2 / 'eplusout.end'
        if end_path.exists():
            [status_case2, runtime_case2] = SuiteRunner.process_end_file(end_path)

        # one quick check here for expect-fatal tests
        if this_entry.basename == 'EMSTestMathAndKill' or this_entry.basename == 'PythonPluginTestMathAndKill':
            if status_case1 == EndErrSummary.STATUS_FATAL and status_case2 == EndErrSummary.STATUS_FATAL:
                # this is actually what we expect, so add a success result, print a message, and get out
                this_entry.add_summary_result(
                    EndErrSummary(
                        EndErrSummary.STATUS_SUCCESS,
                        runtime_case1,
                        EndErrSummary.STATUS_SUCCESS,
                        runtime_case2
                    ))
                return this_entry, "TestMathAndKill Fatal-ed as expected, continuing with no diff checking on it"

        # add the initial end/err summary to the entry
        this_entry.add_summary_result(EndErrSummary(status_case1, runtime_case1, status_case2, runtime_case2))

        # Handle the results of the end file before doing anything with diffs
        # Case 1: Both end files existed, so E+ did complete
        if not any(x == EndErrSummary.STATUS_MISSING for x in [status_case1, status_case2]):
            # Case 1a: Both files are successful
            if sum(x == EndErrSummary.STATUS_SUCCESS for x in [status_case1, status_case2]) == 2:
                ...  # Just continue to process diffs
            # Case 1b: Both completed, but both failed: report that it failed in both cases and return early
            elif sum(x == EndErrSummary.STATUS_SUCCESS for x in [status_case1, status_case2]) == 0:
                return (
                    this_entry,
                    "Skipping entry because it has a fatal error in both base and mod cases: %s" % this_entry.basename
                )
            # Case 1c: Both completed, but one failed: report that it failed in one case and return early
            elif sum(x == EndErrSummary.STATUS_SUCCESS for x in [status_case1, status_case2]) == 1:
                return (
                    this_entry,
                    "Skipping an entry because it appears to have a fatal error in one case: %s" % this_entry.basename
                )
        # Case 2: Both end files DID NOT exist
        elif all(x == EndErrSummary.STATUS_MISSING for x in [status_case1, status_case2]):
            return (
                this_entry,
                "Skipping entry because it failed (crashed) in both base and mod cases: %s" % this_entry.basename
            )
        # Case 3: Both end files DID NOT exist
        elif sum(x == EndErrSummary.STATUS_MISSING for x in [status_case1, status_case2]) == 1:
            return (
                this_entry,
                "Skipping an entry because it appears to have failed (crashed) in one case: %s" % this_entry.basename
            )
        # Case 4: Unhandled combination
        else:  # pragma: no cover -- I don't think we can get here
            return this_entry, "Skipping an entry because it has an unknown end status: %s" % this_entry.basename

        # Load diffing threshold dictionary
        thresh_dict = td.ThreshDict(thresh_dict_file)

        # Do Math (CSV) Diffs
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.csv'):
            this_entry.add_math_differences(MathDifferences(math_diff.math_diff(
                thresh_dict,
                str(case_result_dir_1 / 'eplusout.csv'),
                str(case_result_dir_2 / 'eplusout.csv'),
                str(out_dir / "eplusout.csv.absdiff.csv"),
                str(out_dir / 'eplusout.csv.percdiff.csv'),
                str(out_dir / 'eplusout.csv.diffsummary.csv'),
                path_to_math_diff_log)), MathDifferences.ESO)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusmtr.csv'):
            this_entry.add_math_differences(MathDifferences(math_diff.math_diff(
                thresh_dict,
                str(case_result_dir_1 / 'eplusmtr.csv'),
                str(case_result_dir_2 / 'eplusmtr.csv'),
                str(out_dir / 'eplusmtr.csv.absdiff.csv'),
                str(out_dir / 'eplusmtr.csv.percdiff.csv'),
                str(out_dir / 'eplusmtr.csv.diffsummary.csv'),
                path_to_math_diff_log)), MathDifferences.MTR)

        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'epluszsz.csv'):
            this_entry.add_math_differences(MathDifferences(math_diff.math_diff(
                thresh_dict,
                str(case_result_dir_1 / 'epluszsz.csv'),
                str(case_result_dir_2 / 'epluszsz.csv'),
                str(out_dir / 'epluszsz.csv.absdiff.csv'),
                str(out_dir / 'epluszsz.csv.percdiff.csv'),
                str(out_dir / 'epluszsz.csv.diffsummary.csv'),
                path_to_math_diff_log)), MathDifferences.ZSZ)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusssz.csv'):
            this_entry.add_math_differences(MathDifferences(math_diff.math_diff(
                thresh_dict,
                str(case_result_dir_1 / 'eplusssz.csv'),
                str(case_result_dir_2 / 'eplusssz.csv'),
                str(out_dir / 'eplusssz.csv.absdiff.csv'),
                str(out_dir / 'eplusssz.csv.percdiff.csv'),
                str(out_dir / 'eplusssz.csv.diffsummary.csv'),
                path_to_math_diff_log)), MathDifferences.SSZ)

        # Do sorta-math-diff JSON diff
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout_hourly.json'):
            this_entry.add_math_differences(MathDifferences(SuiteRunner.diff_json_time_series(
                case_result_dir_1 / 'eplusout_hourly.json',
                case_result_dir_2 / 'eplusout_hourly.json',
                out_dir / 'eplusout_hourly.diffs.json')), MathDifferences.JSON)

        # Do Tabular (HTML) Diffs
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplustbl.htm'):
            this_entry.add_table_differences(TableDifferences(table_diff.table_diff(
                thresh_dict,
                str(case_result_dir_1 / 'eplustbl.htm'),
                str(case_result_dir_2 / 'eplustbl.htm'),
                str(out_dir / 'eplustbl.htm.absdiff.htm'),
                str(out_dir / 'eplustbl.htm.percdiff.htm'),
                str(out_dir / 'eplustbl.htm.summarydiff.htm'),
                path_to_table_diff_log)))

        # Do Textual Diffs
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'in.idf'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'in.idf',
                case_result_dir_2 / 'in.idf',
                out_dir / 'in.idf.diff')), TextDifferences.IDF)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.stdout'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.stdout',
                case_result_dir_2 / 'eplusout.stdout',
                out_dir / 'eplusout.stdout.diff')), TextDifferences.STDOUT)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.stderr'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.stderr',
                case_result_dir_2 / 'eplusout.stderr',
                out_dir / 'eplusout.stderr.diff')), TextDifferences.STDERR)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.audit'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.audit',
                case_result_dir_2 / 'eplusout.audit',
                out_dir / 'eplusout.audit.diff')), TextDifferences.AUD)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.bnd'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.bnd',
                case_result_dir_2 / 'eplusout.bnd',
                out_dir / 'eplusout.bnd.diff')), TextDifferences.BND)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.dxf'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.dxf',
                case_result_dir_2 / 'eplusout.dxf',
                out_dir / 'eplusout.dxf.diff')), TextDifferences.DXF)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.eio'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.eio',
                case_result_dir_2 / 'eplusout.eio',
                out_dir / 'eplusout.eio.diff')), TextDifferences.EIO)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout_perflog.csv'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_perf_log(
                case_result_dir_1 / 'eplusout_perflog.csv',
                case_result_dir_2 / 'eplusout_perflog.csv',
                out_dir / 'eplusout_perflog.csv.diff')), TextDifferences.PERF_LOG)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.mdd'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.mdd',
                case_result_dir_2 / 'eplusout.mdd',
                out_dir / 'eplusout.mdd.diff')), TextDifferences.MDD)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.mtd'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.mtd',
                case_result_dir_2 / 'eplusout.mtd',
                out_dir / 'eplusout.mtd.diff')), TextDifferences.MTD)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.rdd'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.rdd',
                case_result_dir_2 / 'eplusout.rdd',
                out_dir / 'eplusout.rdd.diff')), TextDifferences.RDD)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.shd'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.shd',
                case_result_dir_2 / 'eplusout.shd',
                out_dir / 'eplusout.shd.diff')), TextDifferences.SHD)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.err'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.err',
                case_result_dir_2 / 'eplusout.err',
                out_dir / 'eplusout.err.diff')), TextDifferences.ERR)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.delightin'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.delightin',
                case_result_dir_2 / 'eplusout.delightin',
                out_dir / 'eplusout.delightin.diff')), TextDifferences.DL_IN)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.delightout'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.delightout',
                case_result_dir_2 / 'eplusout.delightout',
                out_dir / 'eplusout.delightout.diff')), TextDifferences.DL_OUT)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'readvars.audit'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'readvars.audit',
                case_result_dir_2 / 'readvars.audit',
                out_dir / 'readvars.audit.diff')), TextDifferences.READ_VARS_AUDIT)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.edd'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.edd',
                case_result_dir_2 / 'eplusout.edd',
                out_dir / 'eplusout.edd.diff')), TextDifferences.EDD)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.wrl'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.wrl',
                case_result_dir_2 / 'eplusout.wrl',
                out_dir / 'eplusout.wrl.diff')), TextDifferences.WRL)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.sln'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.sln',
                case_result_dir_2 / 'eplusout.sln',
                out_dir / 'eplusout.sln.diff')), TextDifferences.SLN)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.sci'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.sci',
                case_result_dir_2 / 'eplusout.sci',
                out_dir / 'eplusout.sci.diff')), TextDifferences.SCI)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusmap.csv'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusmap.csv',
                case_result_dir_2 / 'eplusmap.csv',
                out_dir / 'eplusmap.csv.diff')), TextDifferences.MAP)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.dfs'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusout.dfs',
                case_result_dir_2 / 'eplusout.dfs',
                out_dir / 'eplusout.dfs.diff')), TextDifferences.DFS)
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusscreen.csv'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_text_files(
                case_result_dir_1 / 'eplusscreen.csv',
                case_result_dir_2 / 'eplusscreen.csv',
                out_dir / 'eplusscreen.csv.diff')), TextDifferences.SCREEN)

        # sorta textual diff, the GLHE json file
        if SuiteRunner.both_files_exist(case_result_dir_1, case_result_dir_2, 'eplusout.glhe'):
            this_entry.add_text_differences(TextDifferences(SuiteRunner.diff_glhe_files(
                case_result_dir_1 / 'eplusout.glhe',
                case_result_dir_2 / 'eplusout.glhe',
                out_dir / 'eplusout.glhe.diff')), TextDifferences.GLHE)

        # return the updated entry
        return this_entry, "Processed Diffs : %s" % this_entry.basename

    @staticmethod
    def process_end_file(end_path):

        # The end file contains enough info to determine the simulation completion status and runtime
        # success:
        #     EnergyPlus Completed Successfully-- 1 Warning; 0 Severe Errors; Elapsed Time=00hr 00min  1.42sec
        # fatal:
        #     EnergyPlus Terminated--Fatal Error Detected. 0 Warning; 4 Severe Errors; Elapse
        #      d Time=00hr 00min  0.59sec
        # A NEWLINE?? Got to sanitize it.
        with end_path.open(encoding='utf-8') as f_end:
            end_contents = f_end.read().replace("\n", "")

        if "Successfully" in end_contents:
            status = EndErrSummary.STATUS_SUCCESS
        elif "Fatal" in end_contents:
            status = EndErrSummary.STATUS_FATAL
        else:
            return [EndErrSummary.STATUS_UNKNOWN, 0]

        # now process the time string, which is located after a singular equals sign, in the form: 00hr 00min  2.80sec
        # hours and minutes are fixed to 2 decimal points...not sure what happens if it takes over a day...
        # seconds is a floating point that can have 1 or 2 digits before the decimal
        time_string = end_contents.split('=')[1]
        time_string_tokens = time_string.split(' ')
        # remove any blank entries due to duplicated tokens
        time_string_tokens = [x for x in time_string_tokens if x]
        hours = float(time_string_tokens[0][0:2])
        minutes = float(time_string_tokens[1][0:2])
        seconds_term = time_string_tokens[2]
        seconds_index = seconds_term.index('s')
        seconds = float(seconds_term[0:(seconds_index - 1)])
        total_runtime_seconds = hours * 3600.0 + minutes * 60.0 + seconds

        # return results from this end file
        return [status, total_runtime_seconds]

    # diff_logs_for_build creates diff logs between simulations in two build directories
    def diff_logs_for_build(self, original_start_time: datetime):
        self.completed_structure = CompletedStructure(
            self.build_tree_a.source_dir, self.build_tree_a.build_dir,
            self.build_tree_b.source_dir, self.build_tree_b.build_dir,
            self.build_tree_a.build_dir / self.test_output_dir,
            self.build_tree_b.build_dir / self.test_output_dir,
            original_start_time
        )
        diff_runs: list[RunArgs] = []
        for this_entry in self.entries:
            diff_runs.append(
                (
                    this_entry,
                    self.build_tree_a,
                    self.build_tree_b,
                    self.test_output_dir,
                    self.thresh_dict_file
                )
            )

        if self.number_of_threads == 1 or frozen and system() in ['Windows', 'Darwin']:  # pragma: no cover
            if self.number_of_threads > 1:
                self.my_print("Ignoring num_threads on frozen Windows/Mac instance, just running with one thread.")
            for run in diff_runs:
                diff_return = self.diff_wrapper(run)
                self.diff_done(diff_return)
        else:  # for all other applications, run them in a multiprocessing pool
            p = Pool(self.number_of_threads)
            for run in diff_runs:
                p.apply_async(
                    self.diff_wrapper, (run,),
                    callback=self.diff_done,
                    error_callback=lambda e: self.diff_failed(run[0])
                )
            p.close()
            p.join()

    def diff_wrapper(self, run_args: RunArgs):  # pragma: no cover -- this is being skipped by coverage?
        if self.id_like_to_stop_now:
            return run_args[0], "Stopped by request"
        try:
            return_val = SuiteRunner.process_diffs_for_one_case(*run_args)
            return return_val
        except Exception as e:  # pragma: no cover -- I'm not trying to catch every possible case here
            msg = f"Unexpected error processing diffs for {run_args[0].basename},"
            msg += "could indicate an E+ crash caused corrupted files, "
            msg += f"Message: {e}"
            return run_args[0], msg

    def diff_failed(self, this_entry: TestEntry) -> None:
        self.my_print("Error in diffing: %s" % str(this_entry.basename))
        self.my_diff_completed(this_entry.basename)
        self.completed_structure.add_test_entry(this_entry)

    def diff_done(self, results: tuple[TestEntry, str]):
        this_entry, message = results
        self.my_print(message)
        self.my_diff_completed(this_entry.basename)
        self.completed_structure.add_test_entry(this_entry)

    def add_callbacks(self,
                      cb_print: Callable[[str], None],
                      cb_sim_start: Callable[[int], None],
                      cb_case_complete: Callable[[TestCaseCompleted], None],
                      cb_sims_complete: Callable[[], None],
                      cb_diffs_complete: Callable[[], None],
                      cb_all_done: Callable[[CompletedStructure], None],
                      cb_cancel: Callable[[], None]) -> None:
        self.mute = False
        self.print_callback = cb_print
        self.starting_callback = cb_sim_start
        self.case_completed_callback = cb_case_complete
        self.simulations_complete_callback = cb_sims_complete
        self.diff_completed_callback = cb_diffs_complete
        self.all_done_callback = cb_all_done
        self.cancel_callback = cb_cancel

    def my_print(self, msg: str):
        if self.mute:
            return
        if self.print_callback:
            self.print_callback(msg)
            # print(msg) #can uncomment to debug
        else:  # pragma: no cover
            print(msg)

    def my_starting(self, number_of_cases_per_build: int):
        if self.mute:
            return
        if self.starting_callback:
            self.starting_callback(number_of_cases_per_build)
        else:  # pragma: no cover
            self.my_print(
                "Starting runtests, # cases per build = %i" % (
                    number_of_cases_per_build
                )
            )

    def my_case_completed(self, test_case_completed_instance: TestCaseCompleted):
        if self.mute:
            return
        if self.case_completed_callback:
            self.case_completed_callback(test_case_completed_instance)
        else:  # pragma: no cover
            self.my_print(
                "Case complete: %s : %s" % (
                    test_case_completed_instance.run_directory,
                    test_case_completed_instance.case_name
                )
            )

    def my_simulations_complete(self):
        if self.mute:
            return
        if self.simulations_complete_callback:
            self.simulations_complete_callback()
        else:  # pragma: no cover
            self.my_print("Completed all simulations")

    def my_diff_completed(self, case_name: str):
        if self.mute:
            return
        if self.diff_completed_callback:
            self.diff_completed_callback()
        else:  # pragma: no cover
            self.my_print("Completed diffing case: %s" % case_name)

    def my_all_done(self, results: CompletedStructure):
        if self.mute:
            return
        results.extra.set_end_time()
        if self.all_done_callback:
            self.all_done_callback(results)
        else:  # pragma: no cover
            self.my_print("Completed runtests")

    def my_cancelled(self):  # pragma: no cover
        if self.mute:
            return
        if self.cancel_callback:
            self.cancel_callback()
        else:
            self.my_print("Cancelling runtests...")

    def interrupt_please(self):  # pragma: no cover
        self.id_like_to_stop_now = True


if __name__ == "__main__":  # pragma: no cover
    from energyplus_regressions.builds.makefile import CMakeCacheMakeFileBuildDirectory

    # parse command line arguments
    parser = argparse.ArgumentParser(
        description="""
    Run EnergyPlus tests using a specified configuration.  Can be executed in 2 ways:
      1: Arguments can be passed from the command line in the usage here, or
      2: An instance of the SuiteRunner class can be constructed, more useful for UIs or scripting"""
    )
    parser.add_argument('a_build', action="store", help='Path to case a\'s build directory')
    parser.add_argument('b_build', action="store", help='Path to case b\'s build directory')
    parser.add_argument('idf_list_file', action='store', help='Path to the file containing the list of IDFs to run')
    parser.add_argument('output_file', action='store', help='Path to output regression summary json file')
    parser.add_argument('-f', choices=['DD', 'Annual'], help='Force a specific run type', default=None)
    parser.add_argument('-j', action="store", dest="j", type=int, default=1, help='Number of processors to use')
    parser.add_argument('-t', action='store_true', default=False, help='Use this flag to run in test mode')

    args = parser.parse_args()

    run_type = ForceRunType.NONE
    if args.f:
        if args.f == 'DD':
            run_type = ForceRunType.DD
        elif args.f == 'Annual':
            run_type = ForceRunType.ANNUAL

    # For ALL runs use BuildA
    base = CMakeCacheMakeFileBuildDirectory()
    base.run = True
    base.set_build_directory(args.a_build)

    # For now all runs use build B as well (If using ReverseDD, build B can just be None)
    mod = CMakeCacheMakeFileBuildDirectory()
    mod.run = True
    mod.set_build_directory(args.b_build)

    # Do a single test run...
    DoASingleTestRun = args.t

    # Set the expected path for the files_to_run.txt file
    if not args.idf_list_file.exists():
        print("ERROR: Did not find files_to_run.txt at %s; run build_files_to_run first!" % args.idf_list_file)
        sys.exit(1)

    # Build the list of files to run here:
    entries = []
    with args.idf_list_file.open(encoding='utf-8') as f:  # need to ask for this name separately
        json_object = json.loads(f.read())
        for entry in json_object['files_to_run']:
            basename = entry['file']
            if 'epw' in entry:
                epw = entry['epw']
            else:
                epw = None
            entries.append(TestEntry(basename, epw))
            if DoASingleTestRun:
                break

    # Build the run configuration
    RunConfig = TestRunConfiguration(force_run_type=run_type,
                                     single_test_run=DoASingleTestRun,
                                     num_threads=args.j,
                                     report_freq=ReportingFreq.HOURLY,
                                     build_a=base,
                                     build_b=mod)

    # instantiate the test suite
    runner = SuiteRunner(RunConfig, entries)

    # Run it
    runner.run_test_suite()
    response = runner.completed_structure

    print(response.to_json_summary(args.output_file))
