"""Text related utilities"""

import re


def normalize_string(name):
    """Replace any character that is not alphanumeric or underscore with an underscore"""
    name = re.sub(r"\W|^(?=\d)", "_", name)
    # Ensure the name starts with a letter or underscore
    if not re.match(r"^[A-Za-z_]", name):
        name = "_" + name
    return name
