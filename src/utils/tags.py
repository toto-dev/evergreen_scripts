import logging
import re

from collections import OrderedDict

logger = logging.getLogger(__name__)

# Regex to find the block starting with '@tags: [' and ending with ']'
COMMENT_REGEX = r"\s*(?:\*|\/)+\s*"
TAG_HEADER_REGEX = r"@tags:\s*\[\s*"
TAG_FOOTER_REGEX = r"\s*\]"
TAG_REGEX = rf"^({COMMENT_REGEX}){TAG_HEADER_REGEX}(.*?){COMMENT_REGEX}{TAG_FOOTER_REGEX}$"


class Tag:
    def __init__(self, tag_name: str, comments: list):
        self.tag_name = tag_name
        self.comments = comments


def extract_tags_section(file):
    try:
        with open(file, 'r') as f:
            content = f.read()
        tag_match = re.search(TAG_REGEX, content, re.DOTALL|re.MULTILINE)
        if tag_match:
            logger.debug(f'Found matching tag section: {tag_match.groups()}')
            return (tag_match.group(2), tag_match.group(1))
        return None, None
    except Exception as ex:
        raise Exception(f"Failed to extract tags body from file '{file}'") from ex


def line_match_comment(line):
    pattern = rf"^{COMMENT_REGEX}#(.*)$"
    match = re.match(pattern, line)
    return match.group(1) if match else match


def line_match_tag(line):
    pattern = rf"^{COMMENT_REGEX}(?<!#)\b(\S+)\b,$"
    match = re.match(pattern, line)
    return match.group(1) if match else match


def extract_tags(tags_body):
    comments = []
    for line in tags_body.splitlines():
        comment = line_match_comment(line)
        if comment:
            comments.append(comment.strip())
            continue
        tag = line_match_tag(line)
        if tag:
            yield Tag(tag, comments)
            comments = []
            continue
        raise Exception(f"Failed to parse tags line: '{line}'")


class TestTags():
    def __init__(self, tags: OrderedDict, comment_prefix: str):
        self.tags_dict = tags
        self.comment_prefix = comment_prefix

    @staticmethod
    def from_file(file: str):
        tags_body, comment_prefix = extract_tags_section(file)
        if not tags_body:
            return None
        tags_dict = OrderedDict([(tag.tag_name, tag) for tag in extract_tags(tags_body)])
        return TestTags(tags_dict, comment_prefix)

    def serialize(self, indent: int = 2):
        prefix = " " * indent
        lines = ["@tags: ["]
        for tag in self.tags_dict.values():
            for comment in tag.comments:
                lines.append(f"{prefix}# {comment}")
            lines.append(f"{prefix}{tag.tag_name},")
        lines.append("]")
        return f"{self.comment_prefix}" + f"\n{self.comment_prefix}".join(lines)


def replace_tags_body(file, new_tags: TestTags):
    try:
        with open(file, 'r') as f:
            content = f.read()

        new_tags_serialized = new_tags.serialize()
        def replace_fn(match):
            return new_tags_serialized
        new_content = re.sub(TAG_REGEX, replace_fn, content, flags=re.DOTALL|re.MULTILINE)

        # 3. Write the modified content back
        with open(file, 'w') as f:
            f.write(new_content)
    except Exception as ex:
        raise Exception(f"Failed to replace tags in file '{file}'") from ex


def add_tags_to_test(test: str, tags_to_add: list, replace_existing: bool = False):
    tags = TestTags.from_file(test)
    num_tag_modified = 0
    if not tags:
        raise Exception(f"Could not find tags section in test '{test}'")

    for new_tag in tags_to_add:
        if new_tag in tags.tags_dict:
            if not replace_existing or new_tag == tags.tags_dict[new_tag.tag_name]:
                continue
        tags.tags_dict[new_tag.tag_name] = new_tag
        num_tag_modified += 1

    if num_tag_modified:
        replace_tags_body(test, tags)
    return num_tag_modified


def remove_tags_from_test(test: str, tags_to_remove: list, strict: bool = False):
    tags = TestTags.from_file(test)
    num_tags_removed = 0
    if not tags:
        if strict:
            raise Exception(f"Could not find tags section in test '{test}'")
        return num_tags_removed

    for tag in tags_to_remove:
        try:
            tags.tags_dict.pop(tag)
            num_tags_removed += 1
        except KeyError:
            if not strict:
                continue
            raise Exception(f"Cannot find tag '{tag}' in test '{test}'")

    if num_tags_removed:
        replace_tags_body(test, tags)
    return num_tags_removed
