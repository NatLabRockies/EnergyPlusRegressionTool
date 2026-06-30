import os
from pathlib import Path
import shutil
import subprocess
import sys

from energyplus_regressions.builds.base import BuildTree
from energyplus_regressions.structures import ForceRunType


def link_or_copy(source, destination):
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy(source, destination)


class ExecutionArguments:
    def __init__(self, build_tree: BuildTree, entry_name: str, test_run_directory: Path,
                 run_type, min_reporting_freq, this_parametric_file, weather_file_name: str):
        self.build_tree = build_tree
        self.entry_name = entry_name
        self.test_run_directory = test_run_directory
        self.run_type = run_type
        self.min_reporting_freq = min_reporting_freq
        self.this_parametric_file = this_parametric_file
        self.weather_file_name = weather_file_name


# noinspection PyBroadException
def execute_energyplus(e_args: ExecutionArguments) -> tuple[Path, str, bool, bool, str]:
    # set up a few paths
    energyplus = e_args.build_tree.energyplus
    basement = e_args.build_tree.basement
    idd_path = e_args.build_tree.idd_path
    slab = e_args.build_tree.slab
    basement_idd = e_args.build_tree.basementidd
    slab_idd = e_args.build_tree.slabidd
    expand_objects = e_args.build_tree.expandobjects
    ep_macro = e_args.build_tree.epmacro
    read_vars = e_args.build_tree.readvars
    parametric = e_args.build_tree.parametric

    run_directory = e_args.test_run_directory
    std_out = b""
    std_err = b""

    def command_args(executable: Path, *args: str) -> list[str]:
        if executable.suffix.lower() == '.py':
            return [sys.executable, str(executable), *args]
        return [str(executable), *args]

    def run_command(executable: Path, *args: str, env=None, check: bool = False):
        return subprocess.run(
            command_args(executable, *args),
            cwd=run_directory,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check
        )

    try:
        new_idd_path = run_directory / 'Energy+.idd'
        link_or_copy(idd_path, new_idd_path)

        # Copy the weather file into the simulation directory
        if e_args.weather_file_name:
            link_or_copy(e_args.weather_file_name, run_directory / 'in.epw')

        # Run EPMacro as necessary
        idf_file = run_directory / 'in.idf'
        expanded_file = run_directory / 'expanded.idf'
        imf_path = run_directory / 'in.imf'
        ght_file = run_directory / 'GHTIn.idf'
        basement_file = run_directory / 'BasementGHTIn.idf'
        ep_json_file = run_directory / 'in.epJSON'
        rvi_file = run_directory / 'in.rvi'
        mvi_file = run_directory / 'in.mvi'

        if imf_path.exists():
            with imf_path.open('rb') as f:
                lines = f.readlines()
            newlines = []
            for line in lines:
                encoded_line = line.decode('UTF-8', 'ignore')
                if '##fileprefix' in encoded_line:
                    newlines.append('')
                else:
                    newlines.append(encoded_line)
            with imf_path.open('w') as f:
                for line in newlines:
                    f.write(line)
            macro_run = run_command(ep_macro)
            std_out += macro_run.stdout
            std_err += macro_run.stderr
            (run_directory / 'out.idf').rename(idf_file)

        # Run Preprocessor -- after EPMacro?
        if e_args.this_parametric_file:
            parametric_run = run_command(parametric, 'in.idf')
            std_out += parametric_run.stdout
            std_err += parametric_run.stderr
            candidate_files = list(run_directory.glob('in-*.idf'))
            if len(candidate_files) > 0:
                file_to_run_here = sorted(candidate_files)[0]
                if idf_file.exists():
                    idf_file.unlink()
                file_to_run_here.rename(idf_file)
            else:
                return e_args.build_tree.build_dir, e_args.entry_name, False, False, "Issue with Parametric"

        # Run ExpandObjects and process as necessary, but not for epJSON files!
        if idf_file.exists():
            expand_objects_run = run_command(expand_objects)
            std_out += expand_objects_run.stdout
            std_err += expand_objects_run.stderr
            if expanded_file.exists():
                if idf_file.exists():
                    idf_file.unlink()
                expanded_file.rename(idf_file)

                if basement_file.exists():
                    shutil.copy(basement_idd, run_directory)
                    basement_environment = os.environ.copy()
                    basement_environment['CI_BASEMENT_NUMYEARS'] = '2'
                    basement_run = run_command(basement, env=basement_environment)
                    std_out += basement_run.stdout
                    std_err += basement_run.stderr
                    with (run_directory / 'EPObjects.TXT').open() as f:
                        append_text = f.read()
                    with idf_file.open('a') as f:
                        f.write("\n%s\n" % append_text)
                    (run_directory / 'RunINPUT.TXT').unlink()
                    (run_directory / 'RunDEBUGOUT.TXT').unlink()
                    (run_directory / 'EPObjects.TXT').unlink()
                    (run_directory / 'BasementGHTIn.idf').unlink()
                    (run_directory / 'MonthlyResults.csv').unlink()
                    (run_directory / 'BasementGHT.idd').unlink()

                if ght_file.exists():
                    shutil.copy(slab_idd, run_directory)
                    slab_run = run_command(slab)
                    std_out += slab_run.stdout
                    std_err += slab_run.stderr
                    with (run_directory / 'SLABSurfaceTemps.TXT').open() as f:
                        append_text = f.read()
                    with idf_file.open('a') as f:
                        f.write("\n%s\n" % append_text)
                    (run_directory / 'SLABINP.TXT').unlink()
                    (run_directory / 'GHTIn.idf').unlink()
                    (run_directory / 'SLABSurfaceTemps.TXT').unlink()
                    (run_directory / 'SLABSplit Surface Temps.TXT').unlink()
                    (run_directory / 'SlabGHT.idd').unlink()

        # Set up environment
        energyplus_environment = os.environ.copy()
        energyplus_environment["DISPLAYADVANCEDREPORTVARIABLES"] = "YES"
        energyplus_environment["DISPLAYALLWARNINGS"] = "YES"
        if e_args.run_type == ForceRunType.DD:
            energyplus_environment["DDONLY"] = "Y"
            energyplus_environment["REVERSEDD"] = ""
            energyplus_environment["FULLANNUALRUN"] = ""
        elif e_args.run_type == ForceRunType.ANNUAL:
            energyplus_environment["DDONLY"] = ""
            energyplus_environment["REVERSEDD"] = ""
            energyplus_environment["FULLANNUALRUN"] = "Y"
        elif e_args.run_type == ForceRunType.NONE:
            energyplus_environment["DDONLY"] = ""
            energyplus_environment["REVERSEDD"] = ""
            energyplus_environment["FULLANNUALRUN"] = ""
        else:  # pragma: no cover
            # it feels weird to try to test this path...have to set run_type to something invalid?
            # should we just eliminate this else?
            pass  # do nothing?

        # use the user-entered minimum reporting frequency
        #  (useful for limiting to daily outputs for annual simulation, etc.)
        energyplus_environment["MINREPORTFREQUENCY"] = e_args.min_reporting_freq.upper()

        # Execute EnergyPlus
        try:
            energyplus_args = []
            if ep_json_file.exists():
                energyplus_args.append('in.epJSON')
            energyplus_run = run_command(energyplus, *energyplus_args, env=energyplus_environment, check=True)
            std_out += energyplus_run.stdout
            std_err += energyplus_run.stderr
        except subprocess.CalledProcessError as e:  # pragma: no cover
            ...
            # so I can verify that I hit this during the test_case_b_crash test, but if I just have the return in
            #  here alone, it shows as missing on the coverage...wonky
            return e_args.build_tree.build_dir, e_args.entry_name, False, False, str(e)

        # Execute read-vars
        if rvi_file.exists():
            csv_run = run_command(read_vars, 'in.rvi')
        else:
            csv_run = run_command(read_vars)
        std_out += csv_run.stdout
        std_err += csv_run.stderr
        if mvi_file.exists():
            mtr_run = run_command(read_vars, 'in.mvi')
        else:
            with mvi_file.open('w') as f:
                f.write("eplusout.mtr\n")
                f.write("eplusmtr.csv\n")
            mtr_run = run_command(read_vars, 'in.mvi')
        std_out += mtr_run.stdout
        std_err += mtr_run.stderr

        if len(std_out) > 0:
            with (run_directory / 'eplusout.stdout').open('w') as f:
                f.write(std_out.decode('utf-8'))
        if len(std_err) > 0:
            with (run_directory / 'eplusout.stderr').open('w') as f:
                f.write(std_err.decode('utf-8'))

        new_idd_path.unlink()
        return e_args.build_tree.build_dir, e_args.entry_name, True, False, ""

    except Exception as e:
        print("**" + str(e))
        return e_args.build_tree.build_dir, e_args.entry_name, False, False, str(e)
