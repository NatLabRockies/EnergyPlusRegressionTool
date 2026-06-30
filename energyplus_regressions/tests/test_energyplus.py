from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from energyplus_regressions.builds.base import BuildTree
from energyplus_regressions.energyplus import ExecutionArguments, execute_energyplus, link_or_copy
from energyplus_regressions.structures import ReportingFreq, ForceRunType


class TestEnergyPlus(unittest.TestCase):

    def setUp(self):
        cur_dir_path = Path(__file__).resolve().parent
        self.resource_dir = cur_dir_path / 'resources'
        dist_dir = self.resource_dir / 'dist'
        use_windows_binaries = sys.platform.startswith('win')
        self.build_tree = BuildTree()
        self.build_tree.idd_path = self.resource_dir / 'dummy.Energy+.idd'
        self.build_tree.basementidd = self.resource_dir / 'dummy.basement.idd'
        self.build_tree.slabidd = self.resource_dir / 'dummy.slab.py'
        # GH Actions on Windows can execute the packaged dummy exes reliably, while direct shell
        # execution of the .py helpers is flaky for the macro/parametric preprocessors.
        self.build_tree.energyplus = dist_dir / 'energyplus.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.energyplus.py'
        self.build_tree.basement = dist_dir / 'basement.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.basement.py'
        self.build_tree.slab = dist_dir / 'slab.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.slab.py'
        self.build_tree.expandobjects = dist_dir / 'expandobjects.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.expandobjects.py'
        self.build_tree.epmacro = dist_dir / 'epmacro.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.epmacro.py'
        self.build_tree.readvars = dist_dir / 'readvars.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.readvars.py'
        self.build_tree.parametric = dist_dir / 'parametric.exe' if use_windows_binaries \
            else self.resource_dir / 'dummy.parametric.py'
        self.build_tree.build_dir = Path('/dummy/')
        self.run_dir = Path(tempfile.mkdtemp())

    def test_eplus_passed_simple_dd_only(self):
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.DD,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=''
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_passed_simple_dd_only_with_rvi_mvi(self):
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('')
        with (self.run_dir / 'in.rvi').open('w') as f:
            f.write('HI')
        with (self.run_dir / 'in.mvi').open('w') as f:
            f.write('HI')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.DD,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=''
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_passed_simple_annual(self):
        weather_file = self.resource_dir / 'dummy.in.epw'
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.ANNUAL,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=weather_file
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_passed_simple_no_force(self):
        weather_file = self.resource_dir / 'dummy.in.epw'
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.NONE,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=weather_file
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_passed_hvac_template(self):
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('HVACTEMPLATE')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.DD,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=''
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_passed_macro(self):
        with (self.run_dir / 'in.imf').open('w') as f:
            f.write('##fileprefix line\n')
            f.write('line2\n')
            f.write('##fileprefix line3\n')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.DD,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=''
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_passed_parametric(self):
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('PARAMETRIC:')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.DD,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=True,
            weather_file_name=''
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertTrue(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_failed_parametric(self):
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.DD,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=True,
            weather_file_name=''
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertFalse(return_val[2])
        self.assertFalse(return_val[3])

    def test_eplus_failed_invalid_epw(self):
        weather_file = self.resource_dir, 'DOES.NOT.EXIST.in.epw'
        with (self.run_dir / 'in.idf').open('w') as f:
            f.write('')
        return_val = execute_energyplus(ExecutionArguments(
            build_tree=self.build_tree,
            entry_name='entry_name',
            test_run_directory=self.run_dir,
            run_type=ForceRunType.ANNUAL,
            min_reporting_freq=ReportingFreq.HOURLY,
            this_parametric_file=False,
            weather_file_name=weather_file
        ))
        self.assertEqual(Path('/dummy/'), return_val[0])
        self.assertEqual('entry_name', return_val[1])
        self.assertFalse(return_val[2])  # Fail
        self.assertFalse(return_val[3])

    def test_link_or_copy_falls_back_to_copy(self):
        source = self.run_dir / 'source.txt'
        destination = self.run_dir / 'destination.txt'
        source.write_text('contents')

        with patch('energyplus_regressions.energyplus.os.link', side_effect=OSError):
            link_or_copy(source, destination)

        self.assertEqual('contents', destination.read_text())
