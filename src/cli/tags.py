#!/usr/bin/env python2

import click
import logging
import os

from src.utils.tags import Tag, add_tags_to_test, remove_tags_from_test
from src.utils.cli_args import normalize_paths_argument

logger = logging.getLogger(__name__)
MDB_REPO = None


def setup_logging(verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)


@click.group()
@click.option('-v', '--verbose', 'verbose', is_flag=True, show_default=True, default=False, help='Enable debug logs.')
@click.option(
        '--mdb-repo',
        default=os.getenv('MDB_REPO', '.'), show_default=True,
        type=click.Path(exists=True, file_okay=False, dir_okay=True, writable=True, readable=True),
        help='Path to mongoDB repository')
def tags(verbose, mdb_repo):
    """
    helper utility to operate on viewless timseries suites
    """
    setup_logging(verbose)
    global MDB_REPO
    MDB_REPO = mdb_repo

@tags.command()
@click.argument(
        'test_paths',
        nargs=-1,
        type=str)
@click.option(
        '-t', '--tag', 'tag_name',
        required=True,
        help="Name of the tag to add")
@click.option(
        '-c', '--comment',
        help="Comment to add on top of the new tag")
@click.option(
        '-r', '--replace',
        is_flag=True, show_default=True, default=True,
        help='Replace tag and its comment if it already exists')
def add(test_paths, tag_name, comment, replace):
    """
    Add or replace a tag in test files.

    Paths can be separated by spaces, newlines, or commas.
    """
    normalized_path_list = normalize_paths_argument(test_paths)
    logger.debug(f'Test paths: {normalized_path_list}')
    if comment:
        normalized_comments = comment.replace("\\n", "\n").splitlines()
    else:
        normalized_comments = []
    tag = Tag(tag_name, normalized_comments)
    for path in normalized_path_list:
        num_tags_modified = add_tags_to_test(path, [tag], replace)
        if num_tags_modified:
            logger.debug(f"Modified tags for test '{path}'")

@tags.command()
@click.argument(
        'test_paths',
        nargs=-1,
        type=str)
@click.option(
        '-t', '--tag', 'tag_name',
        required=True,
        help="Name of the tag to add")
@click.option(
        '-s', '--strict',
        is_flag=True, show_default=True, default=False,
        help='Throws an error if the file does not have the given tag')
def remove(test_paths, tag_name, strict):
    """
    Remove tag from a test file.

    Paths can be separated by spaces, newlines, or commas.
    """
    normalized_path_list = normalize_paths_argument(test_paths)
    logger.debug(f'Test paths: {normalized_path_list}')
    for path in normalized_path_list:
        num_tags_removed = remove_tags_from_test(path, [tag_name], strict)
        if num_tags_removed:
            logger.debug(f"Removed tag from test '{path}'")

def main():
    tags()

if __name__ == "__main__":
    main()
