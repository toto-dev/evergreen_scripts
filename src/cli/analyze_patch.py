#!/usr/bin/env python2

import click
import logging
import json
import re

from evergreen import RetryingEvergreenApi

logger = logging.getLogger(__name__)

def setup_trace_logging(trace_requests):
    logging.getLogger("urllib3").setLevel(logging.DEBUG if trace_requests else logging.WARNING)
    logging.getLogger("evergreen.api").setLevel(logging.DEBUG if trace_requests else logging.WARNING)

def setup_logging(verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    setup_trace_logging(False)

def get_tests_from_patch(evg_api, patch_id,
        variant_name_pattern = None,
        suite_name_pattern = None,
        test_name_pattern = None,
        skip_inactive=True):

    for build in evg_api.builds_by_version(patch_id):
        variant_name = build.build_variant
        if skip_inactive and not build.activated:
            logger.debug(f"Skipping variant because inactive {variant_name}")
            continue
        if variant_name_pattern and not variant_name_pattern.match(variant_name):
            logger.debug(f"Skipping variant because name does not match {variant_name}")
            continue
        for task in build.get_tasks():
            suite_name = task.display_name
            if skip_inactive and not task.activated:
                logger.debug(f"Skipping suite because inactive {suite_name}")
                continue
            if suite_name_pattern and not suite_name_pattern.match(suite_name):
                logger.debug(f"Skipping suite because name does not match {suite_name}")
                continue
            if not task.finish_time:
                raise Exception(f"Encountered one matching suites that is still in progress {suite_name}")
            for test in task.get_tests():
                test_name = test.test_file
                if test_name_pattern and not test_name_pattern.match(test_name):
                    logger.debug(f"Skipping test  because name does not match {test_name}")
                    continue
                yield {
                    'test_name': test_name,
                    'variant': variant_name,
                    'suite': suite_name,
                    'status': test.status,
                    'duration': test.duration}


@click.group()
@click.option('-v', '--verbose', 'verbose', is_flag=True, show_default=True, default=False, help='Enable debug logs.')
def cli(verbose):
    """
    CLI utility to operate on evregreen patch test results
    """
    setup_logging(verbose)

@cli.command()
@click.option('-p', '--patch', 'patch_id', required=True, help='The ID of the patch to analyze.')
@click.option('--filter-variant', 'variant_name_regex', show_default=True, help='Filter variants using the given regular expression.')
@click.option('--filter-suites', 'suite_name_regex', show_default=True, help='Filter suites using the given regular expression.')
@click.option('--filter-tests', 'test_name_regex', default=r'.*js$', show_default=True, help='Filter tests using the given regular expression.')
@click.option('--trace-requests', 'trace_requests', is_flag=True, show_default=True, default=False, help='Trace network request.')
def get_tests_results(patch_id, variant_name_regex, suite_name_regex, test_name_regex, trace_requests):
    """
    Fetch tests results from an evergeen patch
    """
    setup_trace_logging(trace_requests)
    api = RetryingEvergreenApi.get_api(use_config_file=True)

    variant_name_pattern = re.compile(variant_name_regex) if variant_name_regex else None
    suite_name_pattern = re.compile(suite_name_regex) if suite_name_regex else None
    test_name_pattern = re.compile(test_name_regex) if test_name_regex else None

    tests_results = {}
    with api.with_session() as session:
        for execution_stats in get_tests_from_patch(session, patch_id, variant_name_pattern, suite_name_pattern, test_name_pattern):
            test_name = execution_stats['test_name']
            if test_name not in tests_results:
                tests_results[test_name] = {
                    'test_name': test_name,
                    'num_failed': 0,
                    'num_succeeded': 0,
                    'executions': [],
                    }
            test_result = execution_stats['status']
            if test_result == "pass":
                tests_results[test_name]['num_succeeded'] += 1
            elif test_result == "fail":
                tests_results[test_name]['num_failed'] += 1
            else:
                raise Exception(f'Encountered unexpected test result {test_result} for test {test_name}')
            tests_results[test_name]['executions'].append(execution_stats)
    if not tests_results:
        logger.error("Did not find any matching tests. This could be because the patch is still running or because the requested filters are too strict")
        raise click.Abort()
    print(json.dumps(list(tests_results.values())))

def main():
    cli()

if __name__ == "__main__":
    main()
