"""Local $refs of a joined document that point at nothing."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from jsmn_tools.node import ROOT, Behavior, Location, Node, ObjectNode


@dataclass
class Dangling:
    location: Location
    ref: str


def dangling[E: str](doc: Any, draft: ObjectNode[E]) -> list[Dangling]:
    """Every ``#/pointer`` ref in *doc* whose target is missing.

    Refs inside data (``default``, ``x-*``) are not refs and are skipped,
    as are refs out of the document and plain-name ``#anchor`` fragments.
    """
    found: list[Dangling] = []

    def visit(obj: Any, context: tuple[Node, Behavior], loc: Location) -> None:
        (node, _) = context
        if isinstance(obj, dict):
            for key, val in obj.items():
                if key == "$ref" and not node.opaque:
                    ptr = unquote(val[1:])
                    if (
                        isinstance(val, str)
                        and val.startswith("#/")
                        and not Location.from_pointer(ptr).exists(doc)
                    ):
                        found.append(Dangling(loc, val))
                else:
                    visit(val, node.child(key), loc.push(key))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                visit(item, context, loc.push(str(i)))

    visit(doc, (draft, Behavior()), ROOT)
    return found
