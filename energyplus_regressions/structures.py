import csv
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Optional
from enum import Enum


class ForceRunType:
    DD = "Force Design-day-only simulations"
    ANNUAL = "Force Annual simulations"
    NONE = "Don\'t force anything"

    @staticmethod
    def get_all():
        return [ForceRunType.DD, ForceRunType.ANNUAL, ForceRunType.NONE]


class ReportingFreq:
    DETAILED = "Detailed"
    TIME_STEP = "Timestep"
    HOURLY = "Hourly"
    DAILY = "Daily"
    MONTHLY = "Monthly"
    RUN_PERIOD = "RunPeriod"
    ENVIRONMENT = "Environment"
    ANNUAL = "Annual"

    @staticmethod
    def get_all():
        return [
            ReportingFreq.DETAILED, ReportingFreq.TIME_STEP, ReportingFreq.HOURLY,
            ReportingFreq.DAILY, ReportingFreq.MONTHLY, ReportingFreq.RUN_PERIOD,
            ReportingFreq.ENVIRONMENT, ReportingFreq.ANNUAL
        ]


class ForceOutputSQL(Enum):
    NOFORCE = "Don't force anything"
    SIMPLE = "Simple"
    SIMPLEANDTABULAR = "SimpleAndTabular"


class ForceOutputSQLUnitConversion(Enum):
    NOFORCE = "Don't force anything"
    NONE = "None"
    UseOutputControlTableStyle = 'UseOutputControlTableStyle'
    JtoKWH = 'JtoKWH'
    JtoMJ = 'JtoMJ'
    JtoGJ = 'JtoGJ'
    InchPound = 'InchPound'


class ConfigType(Enum):
    RELEASE = "Release"
    DEBUG = "Debug"


class Results:
    def __init__(self):
        self.descriptions = {}

    def add_to_data(self, base_name: str, suffix: str = None):
        if base_name not in self.descriptions:
            self.descriptions[base_name] = []
        if suffix:
            self.descriptions[base_name].append(f"{base_name} : {suffix}")
        else:
            self.descriptions[base_name].append(f"{base_name}")


class TextDifferences:
    # file types
    AUD = 1
    BND = 2
    DXF = 3
    EIO = 4
    ERR = 5
    MDD = 6
    MTD = 7
    RDD = 8
    SHD = 9
    DL_IN = 10
    DL_OUT = 11
    READ_VARS_AUDIT = 12
    EDD = 13
    WRL = 14
    SLN = 15
    SCI = 16
    MAP = 17
    DFS = 18
    SCREEN = 19
    GLHE = 20
    IDF = 21
    STDOUT = 22
    STDERR = 23
    PERF_LOG = 24
    # diff types
    EQUAL = 1
    DIFFS = 2

    def __init__(self, diff_type):
        self.diff_type = diff_type

    @staticmethod
    def diff_type_to_string(diff_type):
        if diff_type == TextDifferences.EQUAL:
            return 'equal'
        elif diff_type == TextDifferences.DIFFS:
            return 'different'
        else:
            raise Exception('Invalid argument passed in')

    def to_dict(self):
        response = dict()
        response['diff_type'] = self.diff_type_to_string(self.diff_type)
        return response


class MathDifferences:
    ESO = 1
    MTR = 2
    ZSZ = 3
    SSZ = 4
    JSON = 5

    def __init__(self, args_from_math_diff):
        self.diff_type = args_from_math_diff[0]
        self.num_records = args_from_math_diff[1]
        self.count_of_big_diff = args_from_math_diff[2]
        self.count_of_small_diff = args_from_math_diff[3]

    def to_dict(self):
        response = dict()
        response['diff_type'] = self.diff_type
        response['num_records'] = self.num_records
        response['count_of_big_diff'] = self.count_of_big_diff
        response['count_of_small_diff'] = self.count_of_small_diff
        return response


class TableDifferences:
    def __init__(self, args_from_table_diff):
        self.msg = args_from_table_diff[0]
        self.table_count = args_from_table_diff[1]
        self.big_diff_count = args_from_table_diff[2]
        self.small_diff_count = args_from_table_diff[3]
        self.equal_count = args_from_table_diff[4]
        self.string_diff_count = args_from_table_diff[5]
        self.size_err_count = args_from_table_diff[6]
        self.not_in_1_count = args_from_table_diff[7]
        self.not_in_2_count = args_from_table_diff[8]
        self.reordered_table_count = args_from_table_diff[9] if len(args_from_table_diff) > 9 else 0

    def to_dict(self):
        response = dict()
        response['msg'] = self.msg
        response['table_count'] = self.table_count
        response['big_diff_count'] = self.big_diff_count
        response['small_diff_count'] = self.small_diff_count
        response['equal_count'] = self.equal_count
        response['string_diff_count'] = self.string_diff_count
        response['size_err_count'] = self.size_err_count
        response['not_in_1_count'] = self.not_in_1_count
        response['not_in_2_count'] = self.not_in_2_count
        response['reordered_table_count'] = self.reordered_table_count
        return response


class EndErrSummary:
    STATUS_UNKNOWN = 1
    STATUS_SUCCESS = 2
    STATUS_FATAL = 3
    STATUS_MISSING = 4

    def __init__(self, status_case1, runtime_seconds_case1, status_case2, runtime_seconds_case2):
        self.simulation_status_case1 = status_case1
        self.run_time_seconds_case1 = runtime_seconds_case1
        self.simulation_status_case2 = status_case2
        self.run_time_seconds_case2 = runtime_seconds_case2

    @staticmethod
    def status_to_string(status):
        if status == EndErrSummary.STATUS_UNKNOWN:
            return 'unknown'
        elif status == EndErrSummary.STATUS_SUCCESS:
            return 'success'
        elif status == EndErrSummary.STATUS_FATAL:
            return 'fatal'
        elif status == EndErrSummary.STATUS_MISSING:
            return 'missing'
        else:
            raise Exception('Invalid argument passed in')

    def to_dict(self):
        response = dict()
        response['simulation_status_case1'] = self.status_to_string(self.simulation_status_case1)
        if self.simulation_status_case1 == self.STATUS_SUCCESS:
            response['run_time_seconds_case1'] = self.run_time_seconds_case1
        response['simulation_status_case2'] = self.status_to_string(self.simulation_status_case2)
        if self.simulation_status_case2 == self.STATUS_SUCCESS:
            response['run_time_seconds_case2'] = self.run_time_seconds_case2
        return response


class TestEntry:
    __test__ = False  # so that PyTest doesn't try to run this as a class fixture

    def __init__(self, name_relative_to_testfiles_dir: str, epw: str):
        self.name_relative_to_testfiles_dir = name_relative_to_testfiles_dir
        self.basename: str = os.path.splitext(name_relative_to_testfiles_dir.replace(os.path.sep, '__'))[0]
        if epw and epw.endswith('.epw'):
            self.epw = epw[:-4]
        else:  # the basename was passed in already
            self.epw = epw
        self.summary_result = None
        self.eso_diffs = None
        self.mtr_diffs = None
        self.zsz_diffs = None
        self.ssz_diffs = None
        self.table_diffs = None
        self.aud_diffs = None
        self.bnd_diffs = None
        self.dxf_diffs = None
        self.eio_diffs = None
        self.err_diffs = None
        self.mdd_diffs = None
        self.mtd_diffs = None
        self.rdd_diffs = None
        self.shd_diffs = None
        self.dl_in_diffs = None
        self.dl_out_diffs = None
        self.readvars_audit_diffs = None
        self.edd_diffs = None
        self.wrl_diffs = None
        self.sln_diffs = None
        self.sci_diffs = None
        self.map_diffs = None
        self.dfs_diffs = None
        self.screen_diffs = None
        self.glhe_diffs = None
        self.json_diffs = None
        self.idf_diffs = None
        self.stdout_diffs = None
        self.stderr_diffs = None
        self.perf_log_diffs = None

    def add_summary_result(self, end_err_summary):
        self.summary_result = end_err_summary

    def add_math_differences(self, diffs, diff_type):
        if diff_type == MathDifferences.ESO:
            self.eso_diffs = diffs
        elif diff_type == MathDifferences.MTR:
            self.mtr_diffs = diffs
        elif diff_type == MathDifferences.ZSZ:
            self.zsz_diffs = diffs
        elif diff_type == MathDifferences.SSZ:
            self.ssz_diffs = diffs
        elif diff_type == MathDifferences.JSON:
            self.json_diffs = diffs

    def add_text_differences(self, diffs, diff_type):
        if diff_type == TextDifferences.AUD:
            self.aud_diffs = diffs
        elif diff_type == TextDifferences.BND:
            self.bnd_diffs = diffs
        elif diff_type == TextDifferences.DXF:
            self.dxf_diffs = diffs
        elif diff_type == TextDifferences.EIO:
            self.eio_diffs = diffs
        elif diff_type == TextDifferences.ERR:
            self.err_diffs = diffs
        elif diff_type == TextDifferences.MDD:
            self.mdd_diffs = diffs
        elif diff_type == TextDifferences.MTD:
            self.mtd_diffs = diffs
        elif diff_type == TextDifferences.RDD:
            self.rdd_diffs = diffs
        elif diff_type == TextDifferences.SHD:
            self.shd_diffs = diffs
        elif diff_type == TextDifferences.DL_IN:
            self.dl_in_diffs = diffs
        elif diff_type == TextDifferences.DL_OUT:
            self.dl_out_diffs = diffs
        elif diff_type == TextDifferences.READ_VARS_AUDIT:
            self.readvars_audit_diffs = diffs
        elif diff_type == TextDifferences.EDD:
            self.edd_diffs = diffs
        elif diff_type == TextDifferences.WRL:
            self.wrl_diffs = diffs
        elif diff_type == TextDifferences.SLN:
            self.sln_diffs = diffs
        elif diff_type == TextDifferences.SCI:
            self.sci_diffs = diffs
        elif diff_type == TextDifferences.MAP:
            self.map_diffs = diffs
        elif diff_type == TextDifferences.DFS:
            self.dfs_diffs = diffs
        elif diff_type == TextDifferences.SCREEN:
            self.screen_diffs = diffs
        elif diff_type == TextDifferences.GLHE:
            self.glhe_diffs = diffs
        elif diff_type == TextDifferences.IDF:
            self.idf_diffs = diffs
        elif diff_type == TextDifferences.STDOUT:
            self.stdout_diffs = diffs
        elif diff_type == TextDifferences.STDERR:
            self.stderr_diffs = diffs
        elif diff_type == TextDifferences.PERF_LOG:
            self.perf_log_diffs = diffs

    def add_table_differences(self, diffs):
        self.table_diffs = diffs

    def to_dict(self):
        response = dict()
        response['basename'] = self.basename
        response['epw'] = self.epw
        response['summary'] = self.summary_result.to_dict()
        success_1 = self.summary_result.simulation_status_case1 == EndErrSummary.STATUS_SUCCESS
        success_2 = self.summary_result.simulation_status_case1 == EndErrSummary.STATUS_SUCCESS
        if success_1 and success_2:
            if self.table_diffs:
                response['table_diffs'] = self.table_diffs.to_dict()
            if self.eso_diffs:
                response['eso_diffs'] = self.eso_diffs.to_dict()
            if self.mtr_diffs:
                response['mtr_diffs'] = self.mtr_diffs.to_dict()
            if self.zsz_diffs:
                response['zsz_diffs'] = self.zsz_diffs.to_dict()
            if self.ssz_diffs:
                response['ssz_diffs'] = self.ssz_diffs.to_dict()
            if self.aud_diffs:
                response['aud_diffs'] = self.aud_diffs.to_dict()
            if self.bnd_diffs:
                response['bnd_diffs'] = self.bnd_diffs.to_dict()
            if self.dxf_diffs:
                response['dxf_diffs'] = self.dxf_diffs.to_dict()
            if self.eio_diffs:
                response['eio_diffs'] = self.eio_diffs.to_dict()
            if self.err_diffs:
                response['err_diffs'] = self.err_diffs.to_dict()
            if self.mdd_diffs:
                response['mdd_diffs'] = self.mdd_diffs.to_dict()
            if self.mtd_diffs:
                response['mtd_diffs'] = self.mtd_diffs.to_dict()
            if self.rdd_diffs:
                response['rdd_diffs'] = self.rdd_diffs.to_dict()
            if self.shd_diffs:
                response['shd_diffs'] = self.shd_diffs.to_dict()
            if self.dl_in_diffs:
                response['dl_in_diffs'] = self.dl_in_diffs.to_dict()
            if self.dl_out_diffs:
                response['dl_out_diffs'] = self.dl_out_diffs.to_dict()
            if self.readvars_audit_diffs:
                response['readvars_audit_diffs'] = self.readvars_audit_diffs.to_dict()
            if self.edd_diffs:
                response['edd_diffs'] = self.edd_diffs.to_dict()
            if self.wrl_diffs:
                response['wrl_diffs'] = self.wrl_diffs.to_dict()
            if self.sln_diffs:
                response['sln_diffs'] = self.sln_diffs.to_dict()
            if self.sci_diffs:
                response['sci_diffs'] = self.sci_diffs.to_dict()
            if self.map_diffs:
                response['map_diffs'] = self.map_diffs.to_dict()
            if self.dfs_diffs:
                response['dfs_diffs'] = self.dfs_diffs.to_dict()
            if self.screen_diffs:
                response['screen_diffs'] = self.screen_diffs.to_dict()
            if self.glhe_diffs:
                response['glhe_diffs'] = self.glhe_diffs.to_dict()
            if self.json_diffs:
                response['json_diffs'] = self.json_diffs.to_dict()
            if self.idf_diffs:
                response['idf_diffs'] = self.idf_diffs.to_dict()
            if self.stdout_diffs:
                response['stdout_diffs'] = self.stdout_diffs.to_dict()
            if self.stderr_diffs:
                response['stderr_diffs'] = self.stderr_diffs.to_dict()
            if self.perf_log_diffs:
                response['perf_log_diffs'] = self.perf_log_diffs.to_dict()
        return response


class ExtraInfo:
    def __init__(self, start_time):
        self.descriptions = {
            'time_stamps': [
                f"Start time: {start_time}", "End time initialized"
            ]
        }

    def set_end_time(self):
        self.descriptions['time_stamps'][1] = f"End time: {datetime.now()}"


class CompletedStructure:
    def __init__(
            self,
            case_a_source_dir: Path, case_a_build_dir: Path,
            case_b_source_dir: Path, case_b_build_dir: Path,
            results_dir_a: Path, results_dir_b: Path,
            original_start_time: datetime):
        self.case_a_source_dir = case_a_source_dir
        self.case_a_build_dir = case_a_build_dir
        self.case_b_source_dir = case_b_source_dir
        self.case_b_build_dir = case_b_build_dir
        self.results_dir_a = results_dir_a
        self.results_dir_b = results_dir_b
        # results by file
        self.entries_by_file = []
        # results by type
        self.all_files = Results()
        self.success_case_a = Results()
        self.failure_case_a = Results()
        self.success_case_b = Results()
        self.failure_case_b = Results()
        self.total_files_compared = Results()
        self.big_math_diffs = Results()
        self.small_math_diffs = Results()
        self.big_table_diffs = Results()
        self.small_table_diffs = Results()
        self.text_diffs = Results()
        # extra info
        self.extra = ExtraInfo(original_start_time)

    def add_test_entry(self, this_entry):
        self.entries_by_file.append(this_entry)
        # always add the current entry because it was tested
        self.all_files.add_to_data(this_entry.basename)

        # add the entry to the appropriate success/failure bins
        if this_entry.summary_result.simulation_status_case1 == EndErrSummary.STATUS_SUCCESS:
            self.success_case_a.add_to_data(this_entry.basename)
        else:
            self.failure_case_a.add_to_data(this_entry.basename)
        if this_entry.summary_result.simulation_status_case2 == EndErrSummary.STATUS_SUCCESS:
            self.success_case_b.add_to_data(this_entry.basename)
        else:
            self.failure_case_b.add_to_data(this_entry.basename)

        # check the math diffs for this entry
        math_diff_hash = {
            this_entry.eso_diffs: "eso",
            this_entry.mtr_diffs: "mtr",
            this_entry.zsz_diffs: "zsz",
            this_entry.ssz_diffs: "ssz",
            this_entry.json_diffs: "json"
        }
        for diff in math_diff_hash:
            file_type = math_diff_hash[diff]
            if diff:
                self.total_files_compared.add_to_data(this_entry.basename, file_type)
                if diff.count_of_big_diff > 0:
                    self.big_math_diffs.add_to_data(this_entry.basename, file_type)
                elif diff.count_of_small_diff > 0:
                    self.small_math_diffs.add_to_data(this_entry.basename, file_type)

        # get tabular diffs
        if this_entry.table_diffs:
            self.total_files_compared.add_to_data(this_entry.basename, "table")
            if this_entry.table_diffs.big_diff_count > 0:
                self.big_table_diffs.add_to_data(this_entry.basename, "table")
            elif this_entry.table_diffs.small_diff_count > 0:
                self.small_table_diffs.add_to_data(this_entry.basename, "table")
            if this_entry.table_diffs.string_diff_count > 0:
                self.big_table_diffs.add_to_data(this_entry.basename, "table")

        # check the textual diffs
        text_diff_hash = {
            this_entry.aud_diffs: "audit",
            this_entry.bnd_diffs: "bnd",
            this_entry.dxf_diffs: "dxf",
            this_entry.eio_diffs: "eio",
            this_entry.mdd_diffs: "mdd",
            this_entry.mtd_diffs: "mtd",
            this_entry.rdd_diffs: "rdd",
            this_entry.shd_diffs: "shd",
            this_entry.err_diffs: "err",
            this_entry.dl_in_diffs: "delightin",
            this_entry.dl_out_diffs: "delightout",
            this_entry.readvars_audit_diffs: "readvars_audit",
            this_entry.edd_diffs: "edd",
            this_entry.wrl_diffs: "wrl",
            this_entry.sln_diffs: "sln",
            this_entry.sci_diffs: "sci",
            this_entry.map_diffs: "map",
            this_entry.dfs_diffs: "dfs",
            this_entry.screen_diffs: "screen",
            this_entry.glhe_diffs: "glhe",
            this_entry.stdout_diffs: "stdout",
            this_entry.stderr_diffs: "stderr",
            this_entry.perf_log_diffs: "perf_log"
        }
        for diff in text_diff_hash:
            file_type = text_diff_hash[diff]
            if diff:
                self.total_files_compared.add_to_data(this_entry.basename, file_type)
                if diff.diff_type != TextDifferences.EQUAL:
                    self.text_diffs.add_to_data(this_entry.basename, file_type)

    def to_runtime_summary(self, csv_file_path: Path):
        try:
            with open(csv_file_path, "w") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["Case", "Runtime [s]", "Runtime [s]"])
                for this_entry in self.entries_by_file:
                    runtime1 = -1
                    runtime2 = -1
                    if this_entry.summary_result:
                        if this_entry.summary_result.simulation_status_case1 == EndErrSummary.STATUS_SUCCESS:
                            runtime1 = this_entry.summary_result.run_time_seconds_case1
                        if this_entry.summary_result.simulation_status_case2 == EndErrSummary.STATUS_SUCCESS:
                            runtime2 = this_entry.summary_result.run_time_seconds_case2
                    writer.writerow([this_entry.basename, runtime1, runtime2])
        except Exception as this_exception:
            print(this_exception)
            raise this_exception

    def to_json_summary(self, json_file_path: Optional[Path] = None):
        output_data = {
            'directories': {
                'case_a_source': str(self.case_a_source_dir),
                'case_a_build': str(self.case_a_build_dir),
                'case_b_source': str(self.case_b_source_dir),
                'case_b_build': str(self.case_b_build_dir)
            },
            'runs': {
                'all_files': [x for x in self.all_files.descriptions.keys()],
                'success_case_a': [x for x in self.success_case_a.descriptions.keys()],
                'failure_case_a': [x for x in self.failure_case_a.descriptions.keys()],
                'success_case_b': [x for x in self.success_case_b.descriptions.keys()],
                'failure_case_b': [x for x in self.failure_case_b.descriptions.keys()],
                'all_files_compared': [
                    [y for y in self.total_files_compared.descriptions[x]] for x in
                    self.total_files_compared.descriptions.keys()
                ]
            },
            'diffs': {
                'big_math': [x for x in self.big_math_diffs.descriptions.keys()],
                'small_math': [x for x in self.small_math_diffs.descriptions.keys()],
                'big_table': [x for x in self.big_table_diffs.descriptions.keys()],
                'small_table': [x for x in self.small_table_diffs.descriptions.keys()],
                'textual': [x for x in self.text_diffs.descriptions.keys()],
            },
            'results_by_file': [entry.to_dict() for entry in self.entries_by_file],
            'extra': {
                'start_time': self.extra.descriptions['time_stamps'][0],
                'end_time': self.extra.descriptions['time_stamps'][1]
            }
        }
        if json_file_path:
            output_string = json.dumps(output_data, indent=2)
            with open(json_file_path, 'w') as json_file:
                json_file.write(output_string)
        else:
            return output_data
