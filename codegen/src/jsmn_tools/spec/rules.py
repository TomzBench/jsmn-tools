"""What a draft makes of two specs that disagree."""

from collections.abc import Callable
from enum import Enum

from jsmn_tools.node import Location


class Verdict(Enum):
    IGNORE = "ignore"
    WARN = "warning"
    ERROR = "error"


# The verdict on a conflict at a path inside the document.
type ConflictRules = Callable[[Location], Verdict]
