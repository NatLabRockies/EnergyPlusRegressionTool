Introduction
============

This file documents the operations required to utilize EnergyPlusRegressions in
doing development and testing. The program consists of a series of
python scripts, that can be utilized in both a command
line/scripted/non-interactive environment, as well as in a graphical
user interface mode.

The current testing includes regression testing of the example files
that are included in EnergyPlus development.

History/Credits
---------------

This program was based on a test suite used at the National Laboratory
of the Rockies (NLR) (formerly NREL) that was developed by Kyle Benne
and JasonTurner, and consisted of both ruby and python scripts,
including a jobmanager to allow multiple threads to run concurrently.
Although this script was at the heart of the inspiration for creating
this current tool, very little of the original code exists.

The mathematical comparisons performed on the EnergyPlus output files
(MathDiff and TableDiff) were developed originally by Santosh Philip and
improved by Amir Roth. Modifications were made to improve interaction
with the test suite tool and to support Python 3, but the core of the
mathematical comparisons remains.

Build Structure
---------------

This program operates on EnergyPlus build folders and EnergyPlus install
folders. It relies on the build folders having been set up by CMake,
as it parses the CMakeCache to get access to the base source directory.
For installations, it detects the appropriately installed tools relative
to the install folder root.  With the build and source
directories available, the program has everything it needs to run.

Known issues
------------

Known issues for this tool are found on the
`issue list <https://github.com/NatLabRockies/EnergyPlusRegressionTool/issues>`_.
