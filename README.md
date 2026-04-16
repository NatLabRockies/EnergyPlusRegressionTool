# EnergyPlus Regressions

[![Documentation Status](https://readthedocs.org/projects/energyplusregressiontool/badge/?version=latest)](https://energyplusregressiontool.readthedocs.io/en/latest/?badge=latest)
[![Run Tests](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions/workflows/test.yml/badge.svg)](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions/workflows/test.yml)
[![PyPIRelease](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions/workflows/release.yml/badge.svg)](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions/workflows/release.yml)
[![Flake8](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions/workflows/flake8.yml/badge.svg)](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions/workflows/flake8.yml)
[![Coverage Status](https://coveralls.io/repos/github/NatLabRockies/EnergyPlusRegressionTool/badge.svg)](https://coveralls.io/github/NatLabRockies/EnergyPlusRegressionTool)

## Overview

This library provides tools for performing regressions between EnergyPlus builds.
Developers often propose changes to EnergyPlus for:

 - New feature development
 - Defect repair
 - Refactoring for structure or performance

When a developer proposes these changes, those code changes must be tested prior to accepting them into the main branch.
A continuous integration system runs the tests and provides results, but there can be a sometimes lengthy delay waiting on those results, depending on how busy the system is at that time.
This set of tools provides a way to run these regressions locally.

## Usage

This tool works on all three major platforms: Windows, Mac, and Ubuntu (LTS).
GitHub Actions test on multiple platforms, and it is regularly used on all three as well.

To install the tool, simply `pip` install it into your Python environment (either system or virtual environment)
The project page on PyPi is: https://pypi.org/project/energyplus-regressions/.

   - Download using Pip (`pip install energyplus-regressions`).
   - Once installed into the Python install, there will be a binary available to run: `energyplus_regression_runner`.

## Development

For setting up a development environment to do _work_ on this tool, the steps are pretty minimal:
 - Install Python, if needed
 - Clone this repository (`git clone https://github.com/NatLabRockies/EnergyPlusRegressionTool`)
 - Install dependencies (`pip3 install -r requirements.txt`)

## Documentation

Program documentation, including user guide and typical workflows, are available in the documentation.
This documentation is written using RST with Sphinx, and published on [ReadTheDocs](https://energyplusregressiontool.readthedocs.io/en/latest/).

## Testing

Exhaustive unit tests have been added to the "underneath the hood" code, like the functions that calculate diffs and run builds.
The unit tests are run on [Github Actions](https://github.com/NatLabRockies/EnergyPlusRegressionTool/actions).
The GUI code is not unit tested, but tested routinely on all platforms.
