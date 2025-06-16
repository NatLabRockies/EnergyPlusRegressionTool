import os
import random
from subprocess import check_output, CalledProcessError, Popen, call
import sys
import webbrowser
from datetime import datetime
from json import dumps, load as load_json_from_file
from pathlib import Path
from platform import system
from threading import Thread
from time import sleep
from tkinter import (
    Tk, ttk,  # Core pieces
    PhotoImage,  # for taskbar icon
    Frame, Label, LabelFrame, Listbox, Menu, OptionMenu, Scrollbar, Spinbox,  # Widgets
    StringVar,  # Special Types
    messagebox,  # Dialog boxes
    E, W,  # Cardinal directions N, S,
    X, Y, BOTH,  # Orthogonal directions (for fill)
    END, LEFT, TOP,  # relative directions (RIGHT, TOP)
    filedialog, simpledialog,  # system dialogs
)
from typing import List, Union, cast, Literal

from plan_tools.runtime import fixup_taskbar_icon_on_windows
from pubsub import pub

import energyplus_regressions
from energyplus_regressions import VERSION
from energyplus_regressions.builds.base import KnownBuildTypes, autodetect_build_dir_type, BaseBuildDirectoryStructure
from energyplus_regressions.builds.install import EPlusInstallDirectory
from energyplus_regressions.builds.makefile import CMakeCacheMakeFileBuildDirectory
from energyplus_regressions.builds.visualstudio import CMakeCacheVisualStudioBuildDirectory
from energyplus_regressions.epw_map import get_epw_for_idf
from energyplus_regressions.runtests import TestRunConfiguration, SuiteRunner
from energyplus_regressions.structures import (
    CompletedStructure,
    ConfigType,
    ForceOutputSQL,
    ForceOutputSQLUnitConversion,
    ForceRunType,
    ReportingFreq,
    TestEntry,
)


class ResultsTreeRoots:
    NumRun = "Cases run"
    Success1 = "Case 1 Successful runs"
    NotSuccess1 = "Case 1 Unsuccessful run"
    Success2 = "Case 2 Successful runs"
    NotSuccess2 = "Case 2 Unsuccessful run"
    FilesCompared = "Files compared"
    BigMath = "Files with BIG mathdiffs"
    SmallMath = "Files with small mathdiffs"
    BigTable = "Files with BIG tablediffs"
    SmallTable = "Files with small tablediffs"
    Textual = "Files with textual diffs"
    Extra = "Extra Information"

    @staticmethod
    def get_all():
        return [
            ResultsTreeRoots.NumRun,
            ResultsTreeRoots.Success1,
            ResultsTreeRoots.NotSuccess1,
            ResultsTreeRoots.Success2,
            ResultsTreeRoots.NotSuccess2,
            ResultsTreeRoots.FilesCompared,
            ResultsTreeRoots.BigMath,
            ResultsTreeRoots.SmallMath,
            ResultsTreeRoots.BigTable,
            ResultsTreeRoots.SmallTable,
            ResultsTreeRoots.Textual,
        ]


class Notification:
    """
    A thin notification class using gdbus command line calls to avoid any dependencies.
    This should work on most modern Linux distributions.
    """
    def __init__(self, app_name):
        """Construct a new notification class, persisting the app name only"""
        self.command = 'gdbus'
        self.action = 'call'
        self.bus = '--session'
        self.destination = ("--dest", "org.freedesktop.Notifications")
        self.path = ("--object-path", "/org/freedesktop/Notifications")
        self.method = ("--method", "org.freedesktop.Notifications.Notify")
        self.app_name = app_name
        self.notification_id = '0'
        self.actions = '[]'
        self.hint = "{'x-canonical-private-synchronous': <''>, 'transient': <false>, 'value': <20>}"
        self.time_out = '0'  # seems to be ignored, but the notification should stay in the drop-down tray

    def _build_argument_list(self, title: str, message: str, icon_path: Path) -> List[str]:
        """Internal function to construct the full command line based on dynamic arguments"""
        return [
            self.command,
            self.action,
            self.bus,
            self.destination[0], self.destination[1],
            self.path[0], self.path[1],
            self.method[0], self.method[1],
            self.app_name,
            self.notification_id,
            str(icon_path),
            title,
            message,
            self.actions,
            self.hint,
            self.time_out
        ]

    def send_notification(self, title: str, message: str, icon: Path) -> bool:
        """Main action for this class, emits a notification and stores the ID to be reused later"""
        command_line = self._build_argument_list(title, message, icon)
        try:
            # returns: b'(uint32 X,)\n' where X is some int of variable length, so trim from both sides
            std_out = check_output(command_line)
            self.notification_id = std_out[7:-3]
            return True
        except CalledProcessError:
            self.notification_id = '0'
            return False


class PubSubMessageTypes:
    PRINT = '10'
    STARTING = '20'
    CASE_COMPLETE = '30'
    SIMULATIONS_DONE = '40'
    DIFF_COMPLETE = '50'
    ALL_DONE = '60'
    CANCELLED = '70'


class MyApp(Frame):

    def __init__(self):
        self.root = Tk(className='energyplus_regression_runner')
        Frame.__init__(self, self.root)

        # add the taskbar icon, but its having issues reading the png on Mac, not sure.
        if system() == 'Darwin':
            self.icon_path = Path(__file__).resolve().parent / 'icons' / 'icon.icns'
            if self.icon_path.exists():
                self.root.iconbitmap(str(self.icon_path))
            else:
                print(f"Could not set icon for Mac, expecting to find it at {self.icon_path}")
        elif system() == 'Windows':
            self.icon_path = Path(__file__).resolve().parent / 'icons' / 'icon.png'
            img = PhotoImage(file=str(self.icon_path))
            if self.icon_path.exists():
                self.root.iconphoto(False, img)
            else:
                print(f"Could not set icon for Windows, expecting to find it at {self.icon_path}")
        else:  # Linux
            self.icon_path = Path(__file__).resolve().parent / 'icons' / 'icon.png'
            img = PhotoImage(file=str(self.icon_path))
            if self.icon_path.exists():
                self.root.iconphoto(False, img)
            else:
                print(f"Could not set icon for Windows, expecting to find it at {self.icon_path}")
        fixup_taskbar_icon_on_windows(energyplus_regressions.NAME)

        # high level GUI configuration
        self.root.geometry('1000x630')
        self.root.resizable(width=True, height=True)
        self.root.option_add('*tearOff', False)  # keeps file menus from looking weird

        # members related to the background thread and operator instance
        self.long_thread = None
        self.background_operator: Union[None, SuiteRunner] = None

        # tk variables we can access later
        self.label_string = StringVar()
        self.build_dir_1_var = StringVar()
        self.build_dir_2_var = StringVar()
        self.run_period_option = StringVar()
        self.run_period_option.set(ForceRunType.NONE)
        self.reporting_frequency = StringVar()
        self.reporting_frequency.set(ReportingFreq.HOURLY)
        self.force_output_sql = StringVar()
        self.force_output_sql.set(ForceOutputSQL.NOFORCE.value)
        self.force_output_sql_unitconv = StringVar()
        self.force_output_sql_unitconv.set(ForceOutputSQLUnitConversion.NOFORCE.value)
        self.preferred_build_type = StringVar()
        self.preferred_build_type.set(ConfigType.RELEASE.value)
        self.num_threads_var = StringVar()

        # widgets that we might want to access later
        self.build_dir_1_button = None
        self.build_dir_2_button = None
        self.run_button = None
        self.stop_button = None
        if system() == 'Windows':
            self.build_dir_1_var.set(r'C:\EnergyPlus\repos\1eplus\builds\VS64')
            self.build_dir_2_var.set(r'C:\EnergyPlus\repos\2eplus\builds\VS64')
        elif system() == 'Mac':
            self.build_dir_1_var.set('/Users/elee/eplus/repos/1eplus/builds/r')
            self.build_dir_2_var.set('/Users/elee/eplus/repos/2eplus/builds/r')
        elif system() == 'Linux':
            self.build_dir_1_var.set('/eplus/repos/1eplus/builds/r')
            self.build_dir_2_var.set('/eplus/repos/2eplus/builds/r')
        else:
            self.build_dir_1_var.set("<Select build dir 1>")
            self.build_dir_2_var.set("<Select build dir 1>")
        self.progress = None
        self.log_message_listbox = None
        self.results_tree = None
        self.num_threads_spinner = None
        self.full_idf_listbox = None
        self.move_idf_to_active_button = None
        self.active_idf_listbox = None
        self.remove_idf_from_active_button = None
        self.idf_select_all_button = None
        self.idf_select_almost_all_button = None
        self.idf_deselect_all_button = None
        self.idf_select_n_random_button = None
        self.idf_select_from_list_button = None
        self.run_period_option_menu = None
        self.reporting_frequency_option_menu = None
        self.force_output_sql_option_menu = None
        self.force_output_sql_unitconv_option_menu = None
        self.set_preferred_build_type = None
        self.idf_select_from_containing_button = None

        # some data holders
        self.tree_folders = dict()
        self.valid_idfs_in_listing = False
        self.build_1: BaseBuildDirectoryStructure | None = None
        self.build_2: BaseBuildDirectoryStructure | None = None
        self.last_results = None
        self.auto_saving = False
        self.manually_saving = False
        self.save_interval_ms = 60_000  # ms, so 1 minute

        # initialize the GUI
        self.main_notebook = None
        self.init_window()

        # try to autoload the last settings, and kick off the auto-save feature
        self.client_open(auto_open=True)
        # PyCharm is relentlessly complaining the unused *args parameter to root.after, when it's not needed
        # noinspection PyTypeChecker
        self.root.after(self.save_interval_ms, self.auto_save)

        # set up any Var traces here after the init is all done
        self.preferred_build_type.trace_add("write", self.refresh_builds_for_build_type_change)

        # wire up the background thread
        pub.subscribe(self.print_handler, PubSubMessageTypes.PRINT)
        pub.subscribe(self.starting_handler, PubSubMessageTypes.STARTING)
        pub.subscribe(self.case_completed_handler, PubSubMessageTypes.CASE_COMPLETE)
        pub.subscribe(self.runs_complete_handler, PubSubMessageTypes.SIMULATIONS_DONE)
        pub.subscribe(self.diff_complete_handler, PubSubMessageTypes.DIFF_COMPLETE)
        pub.subscribe(self.done_handler, PubSubMessageTypes.ALL_DONE)
        pub.subscribe(self.cancelled_handler, PubSubMessageTypes.CANCELLED)

        # on Linux, initialize the notification class instance
        self.notification: Notification | None = None
        if system() == 'Linux':
            self.notification_icon = Path(self.icon_path)
            self.notification = Notification('energyplus_regression_runner')

    def init_window(self):
        # changing the title of our master widget
        self.root.title("EnergyPlus Regression Tool")
        self.root.protocol("WM_DELETE_WINDOW", self.app_exit)

        # create the menu
        menu = Menu(self.root)
        self.root.config(menu=menu)
        file_menu = Menu(menu)
        file_menu.add_command(label="Open Project...", command=self.client_open)
        file_menu.add_command(label="Save Project...", command=self.client_save)
        file_menu.add_command(label="Exit", command=self.app_exit)
        menu.add_cascade(label="File", menu=file_menu)
        help_menu = Menu(menu)
        help_menu.add_command(label="Open Documentation...", command=self.open_documentation)
        help_menu.add_command(label="About...", command=self.about_dialog)
        menu.add_cascade(label="Help", menu=help_menu)

        # main notebook holding everything
        self.main_notebook = ttk.Notebook(self.root)

        style = ttk.Style()
        style.map("C.TButton",
                  foreground=[('pressed', 'red'), ('active', 'blue')],
                  background=[('pressed', '!disabled', 'black'),
                              ('active', 'white')]
                  )

        # oof, Pycharm is being dumb, not realizing that the X coming from tkinter is indeed just the Literal['x']
        # so I get lots of argument warnings.  I'm going to cast it to a Literal['x'] to make it happy.
        x_type = cast(Literal['x'], X)
        y_type = cast(Literal['y'], Y)
        w_type = cast(Literal['w'], W)
        left_type = cast(Literal['left'], LEFT)
        both_type = cast(Literal['both'], BOTH)
        top_type = cast(Literal['top'], TOP)

        # run configuration
        pane_run = Frame(self.main_notebook)
        group_build_dir_1 = LabelFrame(pane_run, text="Build Directory 1")
        group_build_dir_1.pack(fill=x_type, padx=5)
        self.build_dir_1_button = ttk.Button(group_build_dir_1, text="Change...", command=self.client_build_dir_1,
                                             style="C.TButton")
        self.build_dir_1_button.grid(row=1, column=1, sticky=W)
        build_dir_1_label = Label(group_build_dir_1, textvariable=self.build_dir_1_var)
        build_dir_1_label.grid(row=1, column=2, sticky=E)
        group_build_dir_2 = LabelFrame(pane_run, text="Build Directory 2")
        group_build_dir_2.pack(fill=x_type, padx=5)
        self.build_dir_2_button = ttk.Button(group_build_dir_2, text="Change...", command=self.client_build_dir_2,
                                             style="C.TButton")
        self.build_dir_2_button.grid(row=1, column=1, sticky=W)
        build_dir_2_label = Label(group_build_dir_2, textvariable=self.build_dir_2_var)
        build_dir_2_label.grid(row=1, column=2, sticky=E)
        group_run_options = LabelFrame(pane_run, text="Run Options")
        group_run_options.pack(fill=x_type, padx=5)
        # row 1
        Label(group_run_options, text="Number of threads for suite: ").grid(row=1, column=1, sticky=E)
        self.num_threads_spinner = Spinbox(group_run_options, from_=1, to=48, textvariable=self.num_threads_var)
        self.num_threads_spinner.grid(row=1, column=2, sticky=W)
        # row 2
        Label(group_run_options, text="Test suite run configuration: ").grid(row=2, column=1, sticky=E)
        self.run_period_option_menu = OptionMenu(group_run_options, self.run_period_option, *ForceRunType.get_all())
        self.run_period_option_menu.grid(row=2, column=2, sticky=W)
        # row 3
        Label(group_run_options, text="Minimum reporting frequency: ").grid(row=3, column=1, sticky=E)
        self.reporting_frequency_option_menu = OptionMenu(
            group_run_options, self.reporting_frequency, *ReportingFreq.get_all()
        )
        self.reporting_frequency_option_menu.grid(row=3, column=2, sticky=W)
        # row 4
        Label(group_run_options, text="Force Output SQL: ").grid(row=4, column=1, sticky=E)
        self.force_output_sql_option_menu = OptionMenu(
            group_run_options, self.force_output_sql, *[x.value for x in ForceOutputSQL]
        )
        self.force_output_sql_option_menu.grid(row=4, column=2, sticky=W)
        # row 5
        Label(group_run_options, text="Force Output SQL UnitConv: ").grid(row=5, column=1, sticky=E)
        self.force_output_sql_unitconv_option_menu = OptionMenu(
            group_run_options, self.force_output_sql_unitconv, *[x.value for x in ForceOutputSQLUnitConversion]
        )
        self.force_output_sql_unitconv_option_menu.grid(row=5, column=2, sticky=W)
        # row 6
        Label(group_run_options, text="Multi-configuration Build Preference: ").grid(row=6, column=1, sticky=E)
        self.set_preferred_build_type = OptionMenu(
            group_run_options, self.preferred_build_type, *[x.value for x in ConfigType]
        )
        self.set_preferred_build_type.grid(row=6, column=2, sticky=W)

        self.main_notebook.add(pane_run, text='Configuration')

        # now let's set up a list of checkboxes for selecting IDFs to run
        pane_idfs = Frame(self.main_notebook)
        group_idf_tools = LabelFrame(pane_idfs, text="IDF Selection Tools")
        group_idf_tools.pack(fill=x_type, padx=5)
        self.idf_select_all_button = ttk.Button(
            group_idf_tools, text="Refresh", command=self.build_idf_listing, style="C.TButton"
        )
        self.idf_select_all_button.pack(side=left_type, expand=1)
        self.idf_select_all_button = ttk.Button(
            group_idf_tools, text="Select All", command=self.idf_select_all, style="C.TButton"
        )
        self.idf_select_all_button.pack(side=left_type, expand=1)
        self.idf_select_almost_all_button = ttk.Button(
            group_idf_tools, text="Select All Except Long Runs", command=self.idf_select_all_except_long_runs
        )
        self.idf_select_almost_all_button.pack(side=left_type, expand=1)
        self.idf_deselect_all_button = ttk.Button(
            group_idf_tools, text="Deselect All", command=self.idf_deselect_all, style="C.TButton"
        )
        self.idf_deselect_all_button.pack(side=left_type, expand=1)
        self.idf_select_n_random_button = ttk.Button(
            group_idf_tools, text="Select N Random...", command=self.idf_select_random, style="C.TButton"
        )
        self.idf_select_n_random_button.pack(side=left_type, expand=1)
        self.idf_select_from_list_button = ttk.Button(
            group_idf_tools, text="Select From List...", command=self.idf_select_list, style="C.TButton"
        )
        self.idf_select_from_list_button.pack(side=left_type, expand=1)
        self.idf_select_from_containing_button = ttk.Button(
            group_idf_tools, text="Select Files Containing...", command=self.idf_select_containing, style="C.TButton"
        )
        self.idf_select_from_containing_button.pack(side=left_type, expand=1)

        group_full_idf_list = LabelFrame(pane_idfs, text="Full IDF List")
        group_full_idf_list.pack(fill=both_type, expand=True, padx=5)
        scrollbar = Scrollbar(group_full_idf_list)
        self.full_idf_listbox = Listbox(group_full_idf_list, yscrollcommand=scrollbar.set, selectmode="extended")
        self.full_idf_listbox.bind('<Double-1>', self.idf_move_to_active)
        self.full_idf_listbox.pack(fill=both_type, side=left_type, expand=True)
        scrollbar.pack(fill=y_type, side=left_type)
        scrollbar.config(command=self.full_idf_listbox.yview)

        down_arrows = "  ↓  " * 4
        self.move_idf_to_active_button = ttk.Button(
            pane_idfs, text=down_arrows + "Add to Active List" + down_arrows, command=self.idf_move_to_active,
            style="C.TButton"
        )
        self.move_idf_to_active_button.pack(side=top_type, fill=x_type, expand=False)

        up_arrows = "  ↑  " * 4
        self.remove_idf_from_active_button = ttk.Button(
            pane_idfs, text=up_arrows + "Remove from Active List" + up_arrows, command=self.idf_remove_from_active,
            style="C.TButton"
        )
        self.remove_idf_from_active_button.pack(side=top_type, fill=x_type, expand=False)

        group_active_idf_list = LabelFrame(pane_idfs, text="Active IDF List")
        group_active_idf_list.pack(fill=both_type, expand=True, padx=5)
        scrollbar = Scrollbar(group_active_idf_list)
        self.active_idf_listbox = Listbox(group_active_idf_list, yscrollcommand=scrollbar.set, selectmode="extended")
        self.active_idf_listbox.bind('<Double-1>', self.idf_remove_from_active)
        self.active_idf_listbox.pack(fill=both_type, side=left_type, expand=True)
        scrollbar.pack(fill=y_type, side=left_type)
        scrollbar.config(command=self.active_idf_listbox.yview)

        self.build_idf_listing(initialize=True)

        self.main_notebook.add(pane_idfs, text="IDF Selection")

        # set up a scrolled listbox for the log messages
        frame_log_messages = Frame(self.main_notebook)
        group_log_messages = LabelFrame(frame_log_messages, text="Log Message Tools")
        group_log_messages.pack(fill=x_type, padx=5)
        ttk.Button(group_log_messages, text="Clear Log Messages", command=self.clear_log, style="C.TButton").pack(
            side=left_type, expand=1)
        ttk.Button(group_log_messages, text="Copy Log Messages", command=self.copy_log, style="C.TButton").pack(
            side=left_type, expand=1)
        scrollbar = Scrollbar(frame_log_messages)
        self.log_message_listbox = Listbox(frame_log_messages, yscrollcommand=scrollbar.set)
        self.add_to_log("Program started!")
        self.log_message_listbox.pack(fill=both_type, side=left_type, expand=True)
        scrollbar.pack(fill=y_type, side=left_type)
        scrollbar.config(command=self.log_message_listbox.yview)
        self.main_notebook.add(frame_log_messages, text="Log Messages")

        # set up a tree-view for the results
        frame_results = Frame(self.main_notebook)
        scrollbar = Scrollbar(frame_results)
        self.results_tree = ttk.Treeview(frame_results, columns=("Base File", "Mod File"))
        self.results_tree.bind('<Double-1>', self.results_double_click)
        self.results_tree.bind("<Button-3>", self.results_popup)
        self.results_tree.heading("#0", text="Results")
        self.results_tree.column('#0', minwidth=200, width=200)
        self.results_tree.heading("Base File", text="Base File")
        self.results_tree.column("Base File", minwidth=100, width=100)
        self.results_tree.heading("Mod File", text="Mod File")
        self.results_tree.column("Mod File", minwidth=100, width=100)
        self.build_results_tree()
        self.results_tree.pack(fill=both_type, side=left_type, expand=True)
        scrollbar.pack(fill=y_type, side=left_type)
        scrollbar.config(command=self.results_tree.yview)
        self.main_notebook.add(frame_results, text="Results (initialized)")

        # pack the main notebook on the window
        self.main_notebook.pack(fill=both_type, expand=1)

        # status bar at the bottom
        frame_status = Frame(self.root)
        self.run_button = ttk.Button(frame_status, text="Run", command=self.client_run, style="C.TButton")
        self.run_button.pack(side=left_type, expand=0)
        self.stop_button = ttk.Button(frame_status, text="Stop", command=self.client_stop, state='disabled',
                                      style="C.TButton")
        self.stop_button.pack(side=left_type, expand=0)
        self.progress = ttk.Progressbar(frame_status, length=250)
        self.progress.pack(side=left_type, expand=0)
        label = Label(frame_status, textvariable=self.label_string)
        self.label_string.set("Initialized")
        label.pack(side=left_type, anchor=w_type)
        frame_status.pack(fill=x_type)

    def run(self):
        self.root.mainloop()

    # noinspection PyBroadException
    def client_open(self, auto_open=False):
        if auto_open:
            open_file = os.path.join(os.path.expanduser("~"), ".regression-auto-save.ept")
            if not os.path.exists(open_file):
                return
            open_load_file = open(open_file)
        else:
            open_load_file = filedialog.askopenfile(filetypes=(('ept (json) files', '.ept'),))
        if not open_load_file:
            return
        try:
            data = load_json_from_file(open_load_file)
        except Exception:
            if auto_open:
                return  # just quietly move along
            messagebox.showerror("Load Error", "Could not load file contents as JSON!")
            return
        try:
            self.num_threads_var.set(data['threads'])
            self.run_period_option.set(data['config'])
            self.reporting_frequency.set(data['report_freq'])
            self.force_output_sql.set(data['force_output_sql'])
            self.force_output_sql_unitconv.set(data['force_output_sql_unitconv'])
            if 'preferred_build_type' in data:  # it's initialized to RELEASE in the window __init__, override if found
                self.preferred_build_type.set(data['preferred_build_type'])
            # try to set build 1 object, where it will try to use the preferred build type
            status = self.try_to_set_build_1_to_dir(Path(data['build_1_build_dir']), init_mode=True)
            if status:
                self.build_dir_1_var.set(data['build_1_build_dir'])
            # try to set build 2 object, where it will try to use the preferred build type
            status = self.try_to_set_build_2_to_dir(Path(data['build_2_build_dir']), init_mode=True)
            if status:
                self.build_dir_2_var.set(data['build_2_build_dir'])
            # at this point we should have build dirs, but it's OK if they are invalid
            self.build_idf_listing(False, data['idfs'])
            self.add_to_log("Project settings loaded")
        except Exception:
            if auto_open:
                return  # quietly leave
            messagebox.showerror("Load Error", "Could not load data from project file")

    def auto_save(self):
        if self.manually_saving or self.auto_saving:
            return  # just try again later
        self.client_save(auto_save=True)
        # PyCharm is relentlessly complaining the unused *args parameter to root.after, when it's not needed
        # noinspection PyTypeChecker
        self.root.after(self.save_interval_ms, self.auto_save)

    def client_save(self, auto_save=False):
        # we shouldn't come into this function from the auto_save if any other saving is going on already
        if self.auto_saving:
            # if we get in here from the save menu, and we are already trying to auto-save, give it a sec and retry
            sleep(0.5)
            if self.auto_saving:
                # if we are still auto-saving, then just go ahead and warn
                messagebox.showwarning("Auto-saving was already in process, try again.")
                return
        potential_num_threads = self.num_threads_var.get()
        # noinspection PyBroadException
        try:
            num_threads = int(potential_num_threads)
            idfs = []
            for this_file in self.active_idf_listbox.get(0, END):
                idfs.append(this_file)
            these_results = {}
            if self.last_results:
                these_results = self.last_results.to_json_summary()
            json_object = {
                'config': self.run_period_option.get(),
                'report_freq': self.reporting_frequency.get(),
                'force_output_sql': self.force_output_sql.get(),
                'force_output_sql_unitconv': self.force_output_sql_unitconv.get(),
                'threads': num_threads,
                'idfs': idfs,
                'build_1_build_dir': str(self.build_1.build_directory),
                'build_2_build_dir': str(self.build_2.build_directory),
                'last_results': these_results,
                'preferred_build_type': self.preferred_build_type.get(),
            }
        except Exception as e:
            # if we hit an exception, our action depends on whether we are manually saving or auto-saving
            if auto_save:
                ...  # just return quietly
                print(e)
            else:
                messagebox.showerror(  # issue an error before leaving
                    "Save Error",
                    "Could not save the project because some fields are not yet filled in; "
                    "check inputs including valid build folders"
                )
            return
        if auto_save:
            self.auto_saving = True
            save_file = os.path.join(os.path.expanduser("~"), ".regression-auto-save.ept")
            open_save_file = open(save_file, 'w')
        else:
            self.manually_saving = True
            open_save_file = filedialog.asksaveasfile(defaultextension='.ept')
        if not open_save_file:
            return
        open_save_file.write(dumps(json_object, indent=2))
        open_save_file.close()
        if auto_save:
            self.auto_saving = False
        else:
            self.manually_saving = False

    def results_double_click(self, event):
        cur_item = self.results_tree.item(self.results_tree.focus())
        col = self.results_tree.identify_column(event.x)
        if col == '#1':
            cell_value = cur_item['values'][2]  # hidden column with base directory
        elif col == '#2':
            cell_value = cur_item['values'][3]  # hidden column with mod directory
        else:
            return
        self.open_file_browser_to_directory(cell_value)

    def results_popup(self, event):
        iid = self.results_tree.identify_row(event.y)
        if iid:
            self.results_tree.selection_set(iid)
            cur_item = self.results_tree.item(self.results_tree.focus())
            title = cur_item['text']
            if title.startswith('Case '):
                if title.endswith('(0)'):
                    context_menu = Menu(self, tearoff=0)
                    context_menu.add_command(label="Selected Node Has No Children", command=lambda: None)
                    context_menu.post(event.x_root, event.y_root)
                else:
                    tags = self.results_tree.item(iid, "tags")

                    def copy_lambda():
                        self.copy_selected_node(tags)

                    context_menu = Menu(self, tearoff=0)
                    context_menu.add_command(label="Copy Selected Node Files", command=copy_lambda)
                    context_menu.post(event.x_root, event.y_root)
        else:
            # ignoring anything but the tree root nodes
            pass

    def copy_selected_node(self, tags):
        string = ';'.join(tags)
        self.root.clipboard_clear()
        self.root.clipboard_append(string)

    @staticmethod
    def open_file_browser_to_directory(dir_to_open):
        this_platform = system()
        p = None
        if this_platform == 'Linux':
            try:
                p = Popen(['xdg-open', dir_to_open])
            except Exception as this_exception:  # pragma: no cover - not covering bad directories
                print("Could not open file:")
                print(this_exception)
        elif this_platform == 'Windows':  # pragma: no cover - only testing on Linux
            try:
                p = Popen(['start', dir_to_open], shell=True)
            except Exception as this_exception:
                print("Could not open file:")
                print(this_exception)
        elif this_platform == 'Darwin':  # pragma: no cover - only testing on Linux
            try:
                p = Popen(['open', dir_to_open])
            except Exception as this_exception:
                print("Could not open file:")
                print(this_exception)
        return p

    @staticmethod
    def open_documentation():
        url = 'https://energyplusregressiontool.readthedocs.io/en/latest/'
        # noinspection PyBroadException
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            # error message
            messagebox.showerror("Docs problem", "Could not open documentation in browser")

    @staticmethod
    def about_dialog():
        messagebox.showinfo("About", f"EnergyPlus Regression Tool\nVersion: {VERSION}")

    def build_idf_listing(self, initialize=False, desired_selected_idfs: list[str] = None):
        # if we don't have a specific list, then try to save any already selected ones first

        if desired_selected_idfs:
            desired_selected_idfs = set(desired_selected_idfs)
        else:
            desired_selected_idfs = set()
            for this_file in self.active_idf_listbox.get(0, END):
                desired_selected_idfs.add(this_file)

        # clear any existing ones
        self.active_idf_listbox.delete(0, END)
        self.full_idf_listbox.delete(0, END)

        # now rebuild them
        self.valid_idfs_in_listing = False
        path_1 = Path(self.build_dir_1_var.get())
        path_2 = Path(self.build_dir_2_var.get())
        if path_1.exists() and path_2.exists():
            if not self.build_1:
                bd1 = Path(self.build_dir_1_var.get())
                status = self.try_to_set_build_1_to_dir(bd1)
                if not status:
                    self.full_idf_listbox.insert(END, "Cannot update master list master list")
                    self.full_idf_listbox.insert(END, "Build folder path #1 is invalid")
                    self.full_idf_listbox.insert(END, "Select build folders to fill listing")
                    return
            if not self.build_2:
                bd2 = Path(self.build_dir_2_var.get())
                status = self.try_to_set_build_2_to_dir(bd2)
                if not status:
                    self.full_idf_listbox.insert(END, "Cannot update master list master list")
                    self.full_idf_listbox.insert(END, "Build folder path #2 is invalid")
                    self.full_idf_listbox.insert(END, "Select build folders to fill listing")
                    return
            idf_dir_1 = self.build_1.get_idf_directory()
            idfs_dir_1 = BaseBuildDirectoryStructure.get_idfs_in_dir(idf_dir_1)
            idf_dir_2 = self.build_2.get_idf_directory()
            idfs_dir_2 = BaseBuildDirectoryStructure.get_idfs_in_dir(idf_dir_2)
            common_idfs = idfs_dir_1.intersection(idfs_dir_2)
            if len(common_idfs) == 0:
                self.full_idf_listbox.insert(END, "No common IDFs found between build folders")
                self.full_idf_listbox.insert(END, "Select valid build folders to fill listing")
                return
            for idf in sorted(common_idfs):
                self.full_idf_listbox.insert(END, str(idf))
            self.valid_idfs_in_listing = True
        elif initialize:
            self.full_idf_listbox.insert(END, "This will be the master list")
            self.full_idf_listbox.insert(END, "Select build folders to fill listing")
        elif path_1.exists():
            self.full_idf_listbox.insert(END, "Cannot update master list master list")
            self.full_idf_listbox.insert(END, "Build folder path #2 is invalid")
            self.full_idf_listbox.insert(END, "Select build folders to fill listing")
        elif path_2.exists():
            self.full_idf_listbox.insert(END, "Cannot update master list master list")
            self.full_idf_listbox.insert(END, "Build folder path #1 is invalid")
            self.full_idf_listbox.insert(END, "Select build folders to fill listing")
        else:
            self.full_idf_listbox.insert(END, "Cannot update master list master list")
            self.full_idf_listbox.insert(END, "Both build folders are invalid")
            self.full_idf_listbox.insert(END, "Select build folders to fill listing")

        all_idfs_in_full_list = set(self.full_idf_listbox.get(0, END))
        common_idfs = all_idfs_in_full_list.intersection(desired_selected_idfs)
        for idf in sorted(common_idfs):
            self.active_idf_listbox.insert(END, idf)

    def build_results_tree(self, results: CompletedStructure = None):
        self.results_tree.delete(*self.results_tree.get_children())
        if not results:
            return
        root_and_files = {
            ResultsTreeRoots.NumRun: results.all_files,
            ResultsTreeRoots.Success1: results.success_case_a,
            ResultsTreeRoots.NotSuccess1: results.failure_case_a,
            ResultsTreeRoots.Success2: results.success_case_b,
            ResultsTreeRoots.NotSuccess2: results.failure_case_b,
            ResultsTreeRoots.FilesCompared: results.total_files_compared,
            ResultsTreeRoots.BigMath: results.big_math_diffs,
            ResultsTreeRoots.SmallMath: results.small_math_diffs,
            ResultsTreeRoots.BigTable: results.big_table_diffs,
            ResultsTreeRoots.SmallTable: results.small_table_diffs,
            ResultsTreeRoots.Textual: results.text_diffs,
            ResultsTreeRoots.Extra: results.extra
        }
        case_roots = [
            ResultsTreeRoots.NumRun, ResultsTreeRoots.Success1, ResultsTreeRoots.NotSuccess1,
            ResultsTreeRoots.Success2, ResultsTreeRoots.NotSuccess2
        ]
        for root, these_results in root_and_files.items():
            num_items = sum([len(y) for _, y in these_results.descriptions.items()])
            self.tree_folders[root] = self.results_tree.insert(
                parent="", index=END, text=f"{root} ({num_items})", values=("", "")
            )
            if root in case_roots:
                cases = [k for k in these_results.descriptions.keys()]
                self.results_tree.item(self.tree_folders[root], tags=cases)
            for base_name, result_list in these_results.descriptions.items():
                if root != ResultsTreeRoots.Extra:
                    dir_1 = os.path.join(results.results_dir_a, base_name)
                    dir_2 = os.path.join(results.results_dir_b, base_name)
                    for result in result_list:
                        self.results_tree.insert(
                            parent=self.tree_folders[root], index=END, text=result,
                            values=(
                                "Double click to see base run results",
                                "Double click to see mod run results",
                                dir_1, dir_2
                            )
                        )
                else:  # extra data
                    for result in result_list:
                        self.results_tree.insert(
                            parent=self.tree_folders[root], index=END, text=result
                        )
        self.last_results = results

    def add_to_log(self, message: str):
        if self.log_message_listbox:
            self.log_message_listbox.insert(END, f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]: {message}")
            self.log_message_listbox.yview(END)
        if self.label_string:
            self.label_string.set(message)

    def clear_log(self):
        self.log_message_listbox.delete(0, END)

    def copy_log(self):
        messages = self.log_message_listbox.get(0, END)
        message_string = '\n'.join(messages)
        self.root.clipboard_clear()
        self.root.clipboard_append(message_string)

    def idf_move_to_active(self, _=None):
        if self.long_thread:
            return
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        current_selection = self.full_idf_listbox.curselection()
        if not current_selection:
            messagebox.showerror("IDF Selection Error", "No IDF Selected")
            return
        already_exist_count = 0
        for selection in current_selection:
            currently_selected_idf = self.full_idf_listbox.get(selection)
            try:
                self.active_idf_listbox.get(0, END).index(currently_selected_idf)
                already_exist_count += 1
                continue
            except ValueError:
                pass  # the value error indicates it was _not_ found, so this is success
            self.active_idf_listbox.insert(END, currently_selected_idf)
            self.idf_refresh_count_status(currently_selected_idf, True)
        if already_exist_count > 0:
            messagebox.showwarning("IDF Selection Warning", "At least one IDF was already in active list")

    def idf_remove_from_active(self, event=None):
        if self.long_thread:
            return
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        current_selection = self.active_idf_listbox.curselection()
        if not current_selection:
            if event:
                return
            messagebox.showerror("IDF Selection Error", "No IDF Selected")
            return
        for selection in reversed(current_selection):
            currently_selected_idf = self.active_idf_listbox.get(selection)
            item_index = self.active_idf_listbox.get(0, END).index(currently_selected_idf)
            self.active_idf_listbox.delete(item_index)
            self.idf_refresh_count_status(currently_selected_idf, False)

    def idf_select_all(self):
        self.idf_deselect_all()
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        all_idfs = self.full_idf_listbox.get(0, END)
        for idf in all_idfs:
            self.active_idf_listbox.insert(END, idf)
        self.idf_refresh_count_status()

    def idf_select_all_except_long_runs(self):
        self.idf_deselect_all()
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        all_idfs = self.full_idf_listbox.get(0, END)
        for idf in all_idfs:
            skip_list = [
                'LgOffVAVusingBasement.idf',
                'HospitalLowEnergy.idf',
                'SingleFamilyHouse_HP_Slab_Dehumidification.idf',
                'SingleFamilyHouse_HP_Slab.idf'
            ]
            if idf in skip_list:
                continue
            self.active_idf_listbox.insert(END, idf)
        self.idf_refresh_count_status()

    def idf_deselect_all(self):
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        self.active_idf_listbox.delete(0, END)
        self.idf_refresh_count_status()

    def idf_select_random(self):
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        potential_number_to_select = simpledialog.askinteger("Input Amount", "How many would you like to select?")
        if not potential_number_to_select:
            return
        self.idf_deselect_all()
        number_to_select = int(potential_number_to_select)
        number_of_idf_files = self.full_idf_listbox.size()
        if number_of_idf_files <= number_to_select:  # just take all of them
            self.idf_select_all()
        else:  # down select randomly
            indices_to_take = random.sample(range(number_of_idf_files), number_to_select)
            idfs_to_take = list()
            for i in indices_to_take:
                idf_to_get = self.full_idf_listbox.get(i)
                idfs_to_take.append(idf_to_get)
            for idf_to_get in sorted(idfs_to_take):
                self.active_idf_listbox.insert(END, idf_to_get)
        self.idf_refresh_count_status()

    def idf_select_list(self):
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        idf_names_to_select = simpledialog.askstring("Input IDF Names", "List them semicolon delimited")
        if not idf_names_to_select:
            return
        self.idf_deselect_all()
        idf_names_to_select_sorted = sorted(idf_names_to_select.split(';'))
        for idf_name_to_find in idf_names_to_select_sorted:
            idf_name = idf_name_to_find + '.idf'
            imf_name = idf_name_to_find + '.imf'
            for i in range(self.full_idf_listbox.size()):
                this_idf_possibility = self.full_idf_listbox.get(i)
                if this_idf_possibility == idf_name or this_idf_possibility == imf_name:
                    self.active_idf_listbox.insert(END, this_idf_possibility)
        self.idf_refresh_count_status()

    def idf_select_containing(self):
        if not self.valid_idfs_in_listing:
            messagebox.showerror("IDF Selection Error", "Invalid build folders or IDF list")
            return
        search_string = simpledialog.askstring("Input IDF String", "Plain string to search inside IDFs")
        if not search_string:
            return
        search_string = search_string.upper()
        self.idf_deselect_all()
        for i in range(self.full_idf_listbox.size()):
            this_idf_possibility = self.full_idf_listbox.get(i)
            this_idf_full_path = Path(self.build_1.get_idf_directory()) / this_idf_possibility
            if not this_idf_full_path.exists():
                print(f"Missing IDF at: {this_idf_full_path}")  # some warning?
            contents = this_idf_full_path.read_text().upper()
            if search_string in contents:
                self.active_idf_listbox.insert(END, this_idf_possibility)
        self.idf_refresh_count_status()

    def idf_refresh_count_status(self, test_case=None, checked=False):
        if not self.valid_idfs_in_listing:
            return
        num_total = self.full_idf_listbox.size()
        num_active = self.active_idf_listbox.size()
        if test_case:
            chk_string = "Checked" if checked else "Unchecked"
            if checked:
                self.label_string.set(f"{chk_string} {test_case} ({num_active}/{num_total} selected)")
        else:
            self.label_string.set(f"{num_active}/{num_total} selected")

    def set_gui_status_for_run(self, is_running: bool):
        if is_running:
            run_button_state = 'disabled'
            stop_button_state = 'normal'
            results_tab_title = 'Results (Waiting on current run)'
        else:
            run_button_state = 'normal'
            stop_button_state = 'disabled'
            results_tab_title = 'Results (Up to date)'
        self.build_dir_1_button.configure(state=run_button_state)
        self.build_dir_2_button.configure(state=run_button_state)
        self.run_button.configure(state=run_button_state)
        self.idf_select_all_button.configure(state=run_button_state)
        self.idf_deselect_all_button.configure(state=run_button_state)
        self.idf_select_n_random_button.configure(state=run_button_state)
        self.move_idf_to_active_button.configure(state=run_button_state)
        self.remove_idf_from_active_button.configure(state=run_button_state)
        self.run_period_option_menu.configure(state=run_button_state)
        self.reporting_frequency_option_menu.configure(state=run_button_state)
        self.force_output_sql_option_menu.configure(state=run_button_state)
        self.force_output_sql_unitconv_option_menu.configure(state=run_button_state)
        self.set_preferred_build_type.configure(state=run_button_state)
        self.num_threads_spinner.configure(state=run_button_state)
        self.stop_button.configure(state=stop_button_state)
        self.main_notebook.tab(3, text=results_tab_title)

    def refresh_builds_for_build_type_change(self, *_):
        # just try to refresh both build directories, it will warn if the debug/release folders aren't there
        self.try_to_set_build_1_to_dir(self.build_1.build_directory)
        self.try_to_set_build_2_to_dir(self.build_2.build_directory)

    def add_to_log_and_alert(self, message: str):
        self.add_to_log(message)
        messagebox.showerror("Error", message)

    def try_to_set_build_1_to_dir(self, selected_dir: Path, init_mode: bool = False) -> bool:
        probable_build_dir_type = autodetect_build_dir_type(selected_dir)
        if probable_build_dir_type == KnownBuildTypes.Unknown:
            self.add_to_log("Could not detect build 1 type")
            return False
        elif probable_build_dir_type == KnownBuildTypes.Installation:
            self.add_to_log("Build 1 type detected as an EnergyPlus Install")
            self.build_1 = EPlusInstallDirectory()
            self.build_1.set_build_directory(selected_dir)
        elif probable_build_dir_type == KnownBuildTypes.VisualStudio:
            self.add_to_log("Build 1 type detected as a Visual Studio build")
            self.build_1 = CMakeCacheVisualStudioBuildDirectory()
            self.build_1.set_build_directory(selected_dir)
            if init_mode:
                self.build_1.set_build_mode(ConfigType(self.preferred_build_type.get()), self.add_to_log)
            else:
                self.build_1.set_build_mode(ConfigType(self.preferred_build_type.get()), self.add_to_log_and_alert)
        elif probable_build_dir_type == KnownBuildTypes.Makefile:
            self.add_to_log("Build 1 type detected as a Makefile-style build")
            self.build_1 = CMakeCacheMakeFileBuildDirectory()
            self.build_1.set_build_directory(selected_dir)
        return True

    def client_build_dir_1(self):
        selected_dir = filedialog.askdirectory()
        if not selected_dir:
            return
        p = Path(selected_dir)
        if not p.exists():
            return
        status = self.try_to_set_build_1_to_dir(p)
        if not status:
            messagebox.showerror(
                "Build folder problem", f"Could not determine build type for build 1: {selected_dir}!"
            )
            return
        self.build_dir_1_var.set(str(selected_dir))
        self.build_idf_listing()

    def try_to_set_build_2_to_dir(self, selected_dir: Path, init_mode: bool = False) -> bool:
        probable_build_dir_type = autodetect_build_dir_type(selected_dir)
        if probable_build_dir_type == KnownBuildTypes.Unknown:
            self.add_to_log("Could not detect build 2 type")
            return False
        elif probable_build_dir_type == KnownBuildTypes.Installation:
            self.add_to_log("Build 2 type detected as an EnergyPlus Install")
            self.build_2 = EPlusInstallDirectory()
            self.build_2.set_build_directory(selected_dir)
        elif probable_build_dir_type == KnownBuildTypes.VisualStudio:
            self.add_to_log("Build 2 type detected as a Visual Studio build")
            self.build_2 = CMakeCacheVisualStudioBuildDirectory()
            self.build_2.set_build_directory(selected_dir)
            if init_mode:
                self.build_2.set_build_mode(ConfigType(self.preferred_build_type.get()), self.add_to_log)
            else:
                self.build_2.set_build_mode(ConfigType(self.preferred_build_type.get()), self.add_to_log_and_alert)
        elif probable_build_dir_type == KnownBuildTypes.Makefile:
            self.add_to_log("Build 2 type detected as a Makefile-style build")
            self.build_2 = CMakeCacheMakeFileBuildDirectory()
            self.build_2.set_build_directory(selected_dir)
        return True

    def client_build_dir_2(self):
        selected_dir = filedialog.askdirectory()
        if not selected_dir:
            return
        p = Path(selected_dir)
        if not p.exists():
            return
        status = self.try_to_set_build_2_to_dir(p)
        if not status:
            messagebox.showerror("Could not determine build type for build 2!")
            return
        self.build_dir_2_var.set(selected_dir)
        self.build_idf_listing()

    def client_run(self):
        if self.long_thread:
            messagebox.showerror("Cannot run another thread, wait for the current to finish -- how'd you get here?!?")
            return
        potential_num_threads = self.num_threads_var.get()
        try:
            num_threads = int(potential_num_threads)
        except ValueError:
            messagebox.showerror("Invalid Configuration", "Number of threads must be an integer")
            return
        if not self.build_1:
            messagebox.showerror("Build folder 1 problem", "Select a valid build folder 1 prior to running")
            return
        ok_or_cancel_msg = "Press OK to continue anyway (risky!), or press Cancel to abort"
        build_1_valid = self.build_1.verify()
        if isinstance(self.build_1, CMakeCacheVisualStudioBuildDirectory):
            self.build_1.set_build_mode(ConfigType(self.preferred_build_type.get()), self.add_to_log_and_alert)
        build_1_problem_files = [str(b[1]) for b in build_1_valid if not b[2]]
        if len(build_1_problem_files):
            missing_files = '\n'.join(build_1_problem_files)
            r = messagebox.askokcancel("Build folder 1 problem", f"Missing files:\n{missing_files}\n{ok_or_cancel_msg}")
            if not r:
                return
        if not self.build_2:
            messagebox.showerror("Build folder 2 problem", "Select a valid build folder 2 prior to running")
            return
        build_2_valid = self.build_2.verify()
        if isinstance(self.build_2, CMakeCacheVisualStudioBuildDirectory):
            self.build_2.set_build_mode(ConfigType(self.preferred_build_type.get()), self.add_to_log_and_alert)
        build_2_problem_files = [str(b[1]) for b in build_2_valid if not b[2]]
        if len(build_2_problem_files):
            missing_files = '\n'.join(build_2_problem_files)
            r = messagebox.askokcancel("Build folder 2 problem", f"Missing files:\n{missing_files}\n{ok_or_cancel_msg}")
            if not r:
                return
        run_configuration = TestRunConfiguration(
            force_run_type=self.run_period_option.get(),
            num_threads=num_threads,
            report_freq=self.reporting_frequency.get(),
            force_output_sql=ForceOutputSQL(self.force_output_sql.get()),
            force_output_sql_unitconv=ForceOutputSQLUnitConversion(self.force_output_sql_unitconv.get()),
            build_a=self.build_1,
            build_b=self.build_2
        )
        idfs_to_run = list()
        for this_file in self.active_idf_listbox.get(0, END):
            # using build 1 as the basis for getting a weather file # TODO: Allow different EPWs for build 1, 2
            potential_epw = get_epw_for_idf(self.build_1.source_directory, this_file)
            idfs_to_run.append(
                TestEntry(this_file, potential_epw)
            )
        if len(idfs_to_run) == 0:
            messagebox.showwarning("Nothing to run", "No IDFs were activated, so nothing to run")
            return
        self.background_operator = SuiteRunner(run_configuration, idfs_to_run)
        self.background_operator.add_callbacks(cb_print=MyApp.print_listener,
                                               cb_sim_start=MyApp.starting_listener,
                                               cb_case_complete=MyApp.case_completed_listener,
                                               cb_sims_complete=MyApp.runs_complete_listener,
                                               cb_diffs_complete=MyApp.diff_complete_listener,
                                               cb_all_done=MyApp.done_listener,
                                               cb_cancel=MyApp.cancelled_listener)
        self.set_gui_status_for_run(True)
        self.long_thread = Thread(target=self.background_operator.run_test_suite)
        self.long_thread.daemon = True
        self.add_to_log("Starting a new set of tests")
        self.long_thread.start()

    @staticmethod
    def print_listener(msg: str):
        pub.sendMessage(PubSubMessageTypes.PRINT, msg=msg)

    def print_handler(self, msg):
        self.add_to_log(msg)

    @staticmethod
    def starting_listener(number_of_cases_per_build: int):
        pub.sendMessage(
            PubSubMessageTypes.STARTING,
            number_of_cases_per_build=number_of_cases_per_build
        )

    def starting_handler(self, number_of_cases_per_build: int):
        self.progress['maximum'] = 3 * number_of_cases_per_build
        self.progress['value'] = 0

    @staticmethod
    def case_completed_listener(test_case_completed_instance):
        pub.sendMessage(PubSubMessageTypes.CASE_COMPLETE, test_case_completed_instance=test_case_completed_instance)

    def case_completed_handler(self, test_case_completed_instance):
        self.progress['value'] += 1
        if test_case_completed_instance.run_success:
            message = "Completed %s : %s, Success" % (
                test_case_completed_instance.run_directory, test_case_completed_instance.case_name)
            self.add_to_log(message)
        else:
            message = "Completed %s : %s, Failed" % (
                test_case_completed_instance.run_directory, test_case_completed_instance.case_name)
            self.add_to_log(message)

    @staticmethod
    def runs_complete_listener():
        pub.sendMessage(PubSubMessageTypes.SIMULATIONS_DONE)

    def runs_complete_handler(self):
        self.add_to_log("Simulation runs complete")

    @staticmethod
    def diff_complete_listener():
        pub.sendMessage(PubSubMessageTypes.DIFF_COMPLETE)

    def diff_complete_handler(self):
        self.progress['value'] += 1

    @staticmethod
    def done_listener(results):
        pub.sendMessage(PubSubMessageTypes.ALL_DONE, results=results)

    def done_handler(self, results: CompletedStructure):
        self.add_to_log("All done, finished")
        self.label_string.set("Hey, all done!")
        if system() == 'Linux':
            time_format = '%Y-%m-%d %H:%M:%S.%f'
            time_stamps = results.extra.descriptions['time_stamps']
            start_string = time_stamps[0][12:]
            start_time = datetime.strptime(start_string, time_format)
            end_string = time_stamps[1][10:]
            end_time = datetime.strptime(end_string, time_format)
            time_report = ''
            whole_minutes, remaining_time = divmod((end_time - start_time).total_seconds(), 60)
            if int(whole_minutes) > 0:
                time_report += f'{whole_minutes:.0f}m '
            time_report += f'{remaining_time:.0f}s'
            self.notification.send_notification(
                'EnergyPlus Regression Tool', f'Regressions Finished ({time_report})', self.notification_icon
            )
        elif system() == 'Darwin':
            call([
                'osascript',
                '-e',
                'display notification "Regressions Finished" with title "EnergyPlus Regression Tool"'
            ])
        self.build_results_tree(results)
        self.client_done()

    @staticmethod
    def cancelled_listener():
        pub.sendMessage(PubSubMessageTypes.CANCELLED)

    def cancelled_handler(self):
        self.add_to_log("Cancelled!")
        self.label_string.set("Properly cancelled!")
        self.client_done()

    def client_stop(self):
        self.add_to_log("Attempting to cancel")
        self.label_string.set("Attempting to cancel...")
        self.background_operator.interrupt_please()

    def app_exit(self):
        if self.long_thread:
            messagebox.showerror("Uh oh!", "Cannot exit program while operations are running; abort them then exit")
            return
        self.client_save(auto_save=True)
        sys.exit()

    def client_done(self):
        self.set_gui_status_for_run(False)
        self.long_thread = None
