#!/usr/bin/env python2

import click
import logging
import re
import os
import json
import yaml
import sys

from utils.tags import remove_tag_from_test
from fnmatch import fnmatch
from itertools import chain

logger = logging.getLogger(__name__)
MDB_REPO = None
MATRIX_SUITES_PATH = "buildscripts/resmokeconfig/matrix_suites"
MAPPING_SUITES_FOLDER = f"{MATRIX_SUITES_PATH}/mappings/"
VIEWLESS_OVERRIDES_PATH = f"{MATRIX_SUITES_PATH}/overrides/viewless_timeseries.yml"
OVERRIDE_SECTION_NAME = 'only_validated_jscore_timeseries_tests_selector'

ALL_TESTS_SELECTOR_PREFIX = "all_"
VALIDATED_TESTS_SELECTOR_PREFIX = "only_validated_"
TESTS_SELECTOR_SUFFIX = "_timeseries_tests_selector"
SUITES_NAME_REGEX = r"(?!concurrency)(\S+)"

VIEWLESS_SUITE_EXCLUSION_TAG = "does_not_support_viewless_timeseries_yet"
IGNORED_VIEWLESS_SUITE_EXCLUSION_TAG = f"IGNORE_{VIEWLESS_SUITE_EXCLUSION_TAG}"


def normalize_path(path):
    return os.path.normpath(path.strip(' "'))


def load_viewless_overrides():
    viewless_override_file = os.path.join(MDB_REPO, VIEWLESS_OVERRIDES_PATH)
    with open(viewless_override_file, 'r') as file:
        return yaml.safe_load(file)


def write_viewless_overrides(content):
    viewless_override_file = os.path.join(MDB_REPO, VIEWLESS_OVERRIDES_PATH)
    with open(viewless_override_file, 'w') as file:
        yaml.safe_dump(content, file, default_flow_style=False)


def get_validated_tests_selectors_map():
    # Get the map of all viewless suite overrides
    override_map = {item['name']: item['value'] for item in load_viewless_overrides()}

    selector_map = dict()
    for override_name, override_value in override_map.items():
        validated_match = re.match(rf"{VALIDATED_TESTS_SELECTOR_PREFIX}(\S+){TESTS_SELECTOR_SUFFIX}", override_name)
        if not validated_match:
            # This is not a validated tests selector
            continue

        selector_category_name = validated_match.group(1)

        # find the corresponding all test selector for this suite
        all_tests_selector_name = f"{ALL_TESTS_SELECTOR_PREFIX}{selector_category_name}{TESTS_SELECTOR_SUFFIX}"
        all_tests_selector = override_map[all_tests_selector_name]
        selector_map[selector_category_name] = {
                'all_tests_roots': all_tests_selector['selector']['roots'],
                'validated_tests': override_value['selector']['roots'],
                'validated_tests_selector_name': override_name,
                'all_tests_selector_name': all_tests_selector_name,
                'num_validated_tests': len(override_value['selector']['roots'])
                }
    return selector_map


def update_validated_tests_selectors(selector_map):
    overrides = load_viewless_overrides()

    for selector_cat, selector in selector_map.items():
        selector_name = selector['validated_tests_selector_name']
        for override in overrides:
            if selector_name == override['name']:
                if 'num_validated_tests_added' not in selector:
                    logging.debug(f"Tests selector '{selector_name}' was not modified")
                    continue
                original_num_tests = selector['num_validated_tests']
                final_num_tests = original_num_tests + selector['num_validated_tests_added']
                logging.debug(f"Updating test selector '{selector_name}'. Number of tests increased from {original_num_tests} to {final_num_tests}")
                selector['validated_tests'].sort()
                override['value']['selector']['roots'] = selector['validated_tests']

    write_viewless_overrides(overrides)


def enable_tests_in_viewless_suites(tests, strict=False):
    selector_map = get_validated_tests_selectors_map()

    for test in tests:
        test_matched = False
        for selector_cat, selector in selector_map.items():
            matched_selector = False
            for matcher in selector['all_tests_roots']:
                if fnmatch(test, matcher):
                    logging.debug(f"Found matching category '{selector_cat}' for test '{test}' with matcher '{matcher}'")
                    matched_selector = True
                    break
            if not matched_selector:
                continue

            test_matched = True

            if test in selector['validated_tests']:
                # test already in validated tests
                logging.debug(f"Test '{test}' already included in '{selector['all_tests_selector_name']}'")
                continue

            logging.info(f"Added test '{test}' to {selector['validated_tests_selector_name']}")
            selector['validated_tests'].append(test)
            selector['num_validated_tests_added'] = selector.get('num_validated_tests_added', 0) + 1

        had_exclusion_tag = remove_tag_from_test(test, VIEWLESS_SUITE_EXCLUSION_TAG)
        if had_exclusion_tag:
            logging.info(f"Removed exclusion tag from '{test}'")

        if strict and not test_matched and not had_exclusion_tag:
            raise Exception(f"Failed to add '{test}' to viewless suites. The test doesn't match any validated suite selector and does not contain viewless suite exclusion tag.")

    update_validated_tests_selectors(selector_map)


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

def enable_all_tests_selector():
    """
    Enable all tests selector in viewless timeseries suites
    """
    viewless_suites_folder = os.path.join(MDB_REPO, MAPPING_SUITES_FOLDER)
    pattern = rf"{VALIDATED_TESTS_SELECTOR_PREFIX}{SUITES_NAME_REGEX}{TESTS_SELECTOR_SUFFIX}"
    replacement = rf"{ALL_TESTS_SELECTOR_PREFIX}\1{TESTS_SELECTOR_SUFFIX}"
    replace_string_in_folder(viewless_suites_folder, pattern, replacement)

def enable_validated_tests_selector():
    """
    Enable validated tests selector in viewless timeseries suites
    """
    viewless_suites_folder = os.path.join(MDB_REPO, MAPPING_SUITES_FOLDER)
    pattern = rf"{ALL_TESTS_SELECTOR_PREFIX}{SUITES_NAME_REGEX}{TESTS_SELECTOR_SUFFIX}"
    replacement = rf"{VALIDATED_TESTS_SELECTOR_PREFIX}\1{TESTS_SELECTOR_SUFFIX}"
    replace_string_in_folder(viewless_suites_folder, pattern, replacement)

def set_viewless_suite_exclusion_tag(enable_exclusion_tag):
    viewless_override_path = os.path.join(MDB_REPO, VIEWLESS_OVERRIDES_PATH)
    if enable_exclusion_tag:
        replace_string_in_file(viewless_override_path, f"- {IGNORED_VIEWLESS_SUITE_EXCLUSION_TAG}", f"- {VIEWLESS_SUITE_EXCLUSION_TAG}")
    else:
        replace_string_in_file(viewless_override_path, f"- {VIEWLESS_SUITE_EXCLUSION_TAG}", f"- {IGNORED_VIEWLESS_SUITE_EXCLUSION_TAG}")


@click.group()
@click.option('-v', '--verbose', 'verbose', is_flag=True, show_default=True, default=False, help='Enable debug logs.')
@click.option(
        '--mdb-repo',
        default=os.getenv('MDB_REPO', '.'), show_default=True,
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
    enable_validated_tests_selector()
    set_viewless_suite_exclusion_tag(True)

@viewless_suites.command()
def enable_all_tests():
    """
    Enable all tests in viewless suites
    """
    enable_all_tests_selector()
    set_viewless_suite_exclusion_tag(False)


@viewless_suites.command()
@click.argument(
        'test_paths',
        nargs=-1,
        type=str)
@click.option('-s', '--strict', 'strict',
              is_flag=True, show_default=True, default=False,
              help='Fail if test is already included in test suites.')
def add_tests(test_paths, strict):
    """
    Enable the given list of tests in viewless timeseries suites.

    Paths can be separated by spaces, newlines, or commas.
    """

    has_stdin_data = not sys.stdin.isatty()

    if has_stdin_data and test_paths:
        raise Exception('test paths have been passede both through command line parameter and standard input')

    if not has_stdin_data and not test_paths:
        raise Exception('No test paths provided. Neither through command line parameter nor standard input')

    if has_stdin_data:
        test_paths = [sys.stdin.read().strip()]

    path_list = list(chain.from_iterable(re.split(r'[,\s\n]+', s) for s in test_paths))
    normalized_path_list = list(map(normalize_path, path_list))

    logger.debug(f'Test paths: {normalized_path_list}')
    enable_tests_in_viewless_suites(normalized_path_list, strict)


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
