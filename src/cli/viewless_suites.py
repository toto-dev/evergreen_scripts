#!/usr/bin/env python2

import click
import logging
import re
import os
import json
import yaml

logger = logging.getLogger(__name__)
MDB_REPO = None
VIEWLESS_OVERRIDES_PATH = "buildscripts/resmokeconfig/matrix_suites/overrides/viewless_timeseries.yml"
MAPPING_SUITES_FOLDER = "buildscripts/resmokeconfig/matrix_suites/mappings/"
OVERRIDE_SECTION_NAME = 'only_validated_timeseries_tests_selector'

def update_validated_viewless_tests(new_roots, force_override=False):

    viewless_override_file = os.path.join(MDB_REPO, VIEWLESS_OVERRIDES_PATH)
    # Load the YAML file
    with open(viewless_override_file, 'r') as file:
        overrides = yaml.safe_load(file)

    # Find and update the "only_validated_timeseries_tests_selector" section
    for item in overrides:
        if item.get('name') == OVERRIDE_SECTION_NAME:
            # Update the roots list
            old_roots = item['value']['selector']['roots']
            logger.info(f"Number of validated tests before update {len(old_roots)}")
            for old_root in old_roots:
                if old_root not in new_roots:
                    if not force_override:
                        raise Exception(f"Detected removal of existing test '{old_root}'. Please use --force-override to proceed")
                    else:
                        logger.info(f"Removing existing test {old_root}")
            logger.info(f"Number of validated tests after  update {len(new_roots)}")
            new_roots.sort()
            item['value']['selector']['roots'] = new_roots
            break
    else:
        logger.error(f"Section '{OVERRIDE_SECTION_NAME}' not found.")
        return

    # Write the updated data back to the YAML file
    with open(viewless_override_file, 'w') as file:
        yaml.safe_dump(overrides, file, default_flow_style=False)

def replace_string_in_file(file_path, old_string, new_string):
    with open(file_path, 'r') as file:
        file_data = file.read()

    # Replace the target string
    file_data, num_mod = re.subn(old_string, new_string, file_data)
    if num_mod:
        logging.info(f"Replaced text in file {file_path}")
    with open(file_path, 'w') as file:
        file.write(file_data)

def replace_string_in_folder(folder_path, old_string, new_string):
    for root, _, files in os.walk(folder_path):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            replace_string_in_file(file_path, old_string, new_string)

def setup_logging(verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

@click.group()
@click.option('-v', '--verbose', 'verbose', is_flag=True, show_default=True, default=False, help='Enable debug logs.')
@click.option(
        '--mdb-repo',
        default=os.getenv('MDB_REPO', ''), show_default=True,
        type=click.Path(exists=True, file_okay=False, dir_okay=True, writable=True, readable=True),
        help='Path to mongoDB repository')
def viewless_suites(verbose, mdb_repo):
    """
    helper utility to operate on viewless timseries suites
    """
    setup_logging(verbose)
    global MDB_REPO
    MDB_REPO = mdb_repo

@viewless_suites.command()
def only_validated_tests():
    """
    Enable only validated tests
    """
    viewless_suites_folder = os.path.join(MDB_REPO, MAPPING_SUITES_FOLDER)
    replace_string_in_folder(viewless_suites_folder, 'all_timeseries_tests_selector', 'only_validated_timeseries_tests_selector')

@viewless_suites.command()
def enable_all_tests():
    """
    Enable all tests in viewless suites
    """
    viewless_suites_folder = os.path.join(MDB_REPO, MAPPING_SUITES_FOLDER)
    replace_string_in_folder(viewless_suites_folder, 'only_validated_timeseries_tests_selector', 'all_timeseries_tests_selector')

@viewless_suites.command()
@click.option(
        '--tests-results',
        'tests_results_path',
        default=os.getenv('TESTS_RESULTS', ''), show_default=True,
        type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True),
        help='Path to the folder')
@click.option('--force-override', is_flag=True, show_default=True, default=False, help='Force override of validated tests even if it will cause removal of existing tests.')
def update_validated_tests(tests_results_path, force_override):
    """
    Enable all tests in viewless suites
    """
    with open(tests_results_path, 'r') as file:
        tests_results = json.load(file)

    succeeded_tests = []
    for exec_stats in tests_results:
        test_name = exec_stats['test_name']
        if exec_stats['num_failed'] == 0:
            succeeded_tests.append(test_name)
            continue
        logger.debug(f'Skipping failed test {test_name}')

    for test_name in succeeded_tests:
        logger.info(f'Test succeeded {test_name}')

    update_validated_viewless_tests(succeeded_tests, force_override)


def main():
    viewless_suites()

if __name__ == "__main__":
    main()
