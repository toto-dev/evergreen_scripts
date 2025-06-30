import os
import sys
import re

from itertools import chain

def normalize_path(path):
    return os.path.normpath(path.strip(' "'))


def normalize_paths_argument(paths):
    has_stdin_data = not sys.stdin.isatty()

    if has_stdin_data and paths:
        raise Exception('test paths have been passede both through command line parameter and standard input')

    if not has_stdin_data and not paths:
        raise Exception('No test paths provided. Neither through command line parameter nor standard input')

    if has_stdin_data:
        paths = [sys.stdin.read().strip()]

    for test in paths:
        if not test:
            raise Exception(f"Unable to process empty test path '{test}'")

    path_list = list(chain.from_iterable(re.split(r'[,\s\n]+', s) for s in paths))
    return list(map(normalize_path, path_list))
