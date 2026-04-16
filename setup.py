import os
from platform import system
from setuptools import setup

from energyplus_regressions import NAME, VERSION

this_dir = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_dir, 'README.md'), encoding='utf-8') as i_file:
    long_description = i_file.read()


install_requires = ['PyPubSub', 'beautifulsoup4==4.14.3', 'PLAN-Tools>=0.7']
if system() == 'Windows':
    install_requires.append('pypiwin32')

setup(
    name=NAME,
    version=VERSION,
    packages=['energyplus_regressions', 'energyplus_regressions.builds', 'energyplus_regressions.diffs'],
    include_package_data=True,
    package_data={
        'energyplus_regressions': ['diffs/math_diff.config', 'icons/icon.png', 'icons/icon.ico', 'icons/icon.icns']
    },
    url='https://github.com/NatLabRockies/EnergyPlusRegressionTool',
    license='ModifiedBSD',
    author='Edwin Lee, for NLR, for United States Department of Energy',
    description='A Python 3 library for evaluating regressions between EnergyPlus builds.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    install_requires=install_requires,
    entry_points={
        'gui_scripts': [
            'energyplus_regression_runner=energyplus_regressions.runner:main_gui',
        ],
        'console_scripts': [
            'energyplus_regression_configure=energyplus_regressions.configure:configure_cli',
        ],
    },
    python_requires='>=3.9',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Physics',
        'Topic :: Utilities',
    ],
    platforms=[
        'Linux (Tested on Ubuntu)', 'MacOSX', 'Windows'
    ],
    keywords=[
        'energyplus_launch', 'ep_launch',
        'EnergyPlus', 'eplus', 'Energy+',
        'Building Simulation', 'Whole Building Energy Simulation',
        'Heat Transfer', 'HVAC', 'Modeling',
    ]
)
