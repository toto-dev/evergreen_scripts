import logging
import re

logger = logging.getLogger(__name__)

# Regex to find the block starting with '@tags: [' and ending with ']'
TAG_REGEX = r"(@tags:\s*\[\s*)(.*)(\s*])"
COMMENT_REGEX = r"\s*(\*|\/)+\s*"

def get_tags_body(file):
    try:
        with open(file, 'r') as f:
            content = f.read()
        tag_match = re.search(TAG_REGEX, content, re.DOTALL|re.MULTILINE)
        if tag_match:
            return tag_match.group(2)
        return None
    except Exception as ex:
        raise Exception(f"Failed to extract tags body from file '{file}'") from ex


def replace_tags_body(file, tags_body):
    try:
        with open(file, 'r') as f:
            content = f.read()

        def replace_fn(match):
            return match.group(1) + tags_body + match.group(3)
        new_content = re.sub(TAG_REGEX, replace_fn, content, flags=re.DOTALL|re.MULTILINE)

        # 3. Write the modified content back
        with open(file, 'w') as f:
            f.write(new_content)
    except Exception as ex:
        raise Exception(f"Failed to replace tags in file '{file}'") from ex


def line_match_comment(line):
    pattern = rf"^{COMMENT_REGEX}#.*$"
    return re.match(pattern, line)


def line_match_tag(line, tag):
    pattern = rf"^{COMMENT_REGEX}(?<!#)\b{tag}\b,$"
    return re.match(pattern, line)


def remove_tag_from_body(tags_body, tag):
    redacted = []
    buffer = []
    for line in tags_body.splitlines():
        if line_match_comment(line):
            buffer.append(line)
        elif line_match_tag(line, tag):
            buffer = []
        else:
            redacted.extend(buffer)
            buffer = []
            redacted.append(line)
    return '\n'.join(redacted)


def remove_tag_from_test(test, tag):
    tags_body = get_tags_body(test)
    if not tags_body or not re.search(tag, tags_body):
        return False
    new_body = remove_tag_from_body(tags_body, tag)
    replace_tags_body(test, new_body)
    return True
