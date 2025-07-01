import logging
import re

from collections import OrderedDict

logger = logging.getLogger(__name__)

# Regex to find the block starting with '@tags: [' and ending with ']'
SPACE = "[ \t]"
COMMENT_REGEX = rf"{SPACE}*(?:\*|\/)*{SPACE}*"
TAG_HEADER_REGEX = rf"@tags:{SPACE}*\[{SPACE}*"
TAG_FOOTER_REGEX = rf"{SPACE}*\]"
TAG_REGEX = rf"^({COMMENT_REGEX}){TAG_HEADER_REGEX}(.*?){COMMENT_REGEX}{TAG_FOOTER_REGEX}$"


class Tag:
    def __init__(self, tag_name: str, comments: list = []):
        self.tag_name = tag_name
        self.comments = comments

def extract_tags_section(file):
    try:
        with open(file, 'r') as f:
            content = f.read()
        tag_match = re.search(TAG_REGEX, content, re.DOTALL|re.MULTILINE)
        if tag_match:
            logger.debug(f"Found matching tag section in '{file}': {tag_match.groups()}")
            return (tag_match.group(2), tag_match.group(1))
        return None, None
    except Exception as ex:
        raise Exception(f"Failed to extract tags body from file '{file}'") from ex


def extract_tags(tags_body):
    comments = []
    lines = tags_body.strip('\n,').splitlines()
    for full_line in lines:
        if not full_line:
            # skip empty line
            continue
        match = re.match(rf"^{COMMENT_REGEX}(.*)[\s,]*$", full_line)
        if not match:
            raise Exception(f"Failed to remove comment header from tags line: '{full_line}'")
        line = match.group(1)

        match_line_with_comment = re.match(r"(\s*\S+\s*,\s*)?#\s?(.*)", line)
        if match_line_with_comment:
            comments.append(match_line_with_comment.group(2))
            if match_line_with_comment.group(1):
                tag_name = match_line_with_comment.group(1).strip(', ')
                yield Tag(tag_name, comments)
                comments = []
            continue

        tags = line.split(',')
        for tag in tags:
            if not tag:
                # skip empty line
                continue
            yield Tag(tag.strip(), comments)
            comments = []


def extract_indent(tags_body, comment_prefix):
    if not tags_body.startswith('\n'):
        # this is a single line tag section
        # so no indent to extract
        return None
    lines = tags_body.strip('\n').splitlines()
    if not lines:
        return None
    first_line = lines[0]
    pattern = rf"^{re.escape(comment_prefix)}({SPACE}*).*$"
    match = re.match(pattern, first_line)
    if not match:
        raise Exception(f"Failed to extract indent from tags line: '{first_line}'. Comment prefix: '{comment_prefix}'")
    return len(match.group(1))


class TestTags():
    def __init__(self, tags: OrderedDict, comment_prefix: str, indent: int = 2):
        self.tags_dict = tags
        self.comment_prefix = comment_prefix
        self.indent = indent if indent is not None else 2

    @staticmethod
    def from_file(file: str):
        tags_body, comment_prefix = extract_tags_section(file)
        if not tags_body:
            return None
        indent = extract_indent(tags_body, comment_prefix)
        tags_dict = OrderedDict([(tag.tag_name, tag) for tag in extract_tags(tags_body)])
        return TestTags(tags_dict, comment_prefix, indent)

    def serialize(self):
        prefix = " " * self.indent
        lines = ["@tags: ["]
        for tag in self.tags_dict.values():
            for comment in tag.comments:
                lines.append(f"{prefix}# {comment}")
            lines.append(f"{prefix}{tag.tag_name},")
        lines.append("]")
        return f"{self.comment_prefix}" + f"\n{self.comment_prefix}".join(lines)


def find_header_comment_end(file_content):
    in_comment = False
    is_multiline = True
    line_num = 0
    for line in file_content.splitlines():
        line_num += 1
        if not line and not in_comment:
            continue
        if re.match(rf"^{SPACE}*(\*|\/)+{SPACE}*", line):
            is_multiline  = not line.strip().startswith('//')
            in_comment = True
            continue
        break
    last_comment_line = line_num - 1
    if is_multiline:
        last_comment_line -= 1
    if last_comment_line < 0:
        last_comment_line = 0
    return (last_comment_line, is_multiline)


def add_tags_section(file_content: str, new_tags: TestTags):
    line_num, multiline_comment = find_header_comment_end(file_content)
    new_tags.comment_prefix = ' * ' if multiline_comment else '// '
    if not line_num:
        serialized_tags = f"/*\n{new_tags.serialize()}\n */"
    else:
        serialized_tags = f"{new_tags.serialize()}\n"

    file_content_lines = file_content.splitlines()
    file_content_lines.insert(line_num, serialized_tags)
    return "\n".join(file_content_lines)


def write_tags_section(file, new_tags: TestTags):
    try:
        with open(file, 'r') as f:
            content = f.read()

        has_tags_section = re.search(TAG_REGEX, content, flags=re.DOTALL|re.MULTILINE)
        if has_tags_section:
            if not new_tags.tags_dict:
                logger.debug(f"Removing tags section from '{file}'")
                new_tags_serialized = ""
            else:
                logger.debug(f"Updating tags of '{file}'")
                new_tags_serialized = new_tags.serialize() if new_tags.tags_dict else ""
            new_content = re.sub(rf"{TAG_REGEX}\n?", f"{new_tags_serialized}\n", content, flags=re.DOTALL|re.MULTILINE)
        else:
            if not new_tags.tags_dict:
                # tags list is empty and the file does not have any tags section yet
                return
            logger.debug(f"Adding tags section to '{file}'")
            new_content = add_tags_section(content, new_tags)

        # 3. Write the modified content back
        with open(file, 'w') as f:
            f.write(new_content)
    except Exception as ex:
        raise Exception(f"Failed to replace tags in file '{file}'") from ex


def add_tags_to_test(test: str, tags_to_add: list, replace_existing: bool = False):
    tags = TestTags.from_file(test)
    if not tags:
        tags = TestTags(OrderedDict(), '')

    num_tag_modified = 0
    for new_tag in tags_to_add:
        if new_tag in tags.tags_dict:
            if not replace_existing or new_tag == tags.tags_dict[new_tag.tag_name]:
                continue
        tags.tags_dict[new_tag.tag_name] = new_tag
        num_tag_modified += 1

    if num_tag_modified:
        write_tags_section(test, tags)
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
        write_tags_section(test, tags)
    return num_tags_removed
