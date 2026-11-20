"""Local $refs of a joined document that point at nothing."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from jsmn_tools.node import ROOT, Behavior, Location, ObjectNode

from .children import Context, entries, is_ref, items


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

    def visit(obj: Any, context: Context, loc: Location) -> None:
        match obj:
            case dict():
                for key, child in entries(obj, context, loc):
                    if is_ref(key, child.value, context):
                        val: str = child.value
                        ptr = unquote(val[1:])
                        if val.startswith("#/") and not Location.from_pointer(
                            ptr
                        ).exists(doc):
                            found.append(Dangling(loc, val))
                    else:
                        visit(*child)
            case list():
                for child in items(obj, context, loc):
                    visit(*child)

    visit(doc, (draft, Behavior()), ROOT)
    return found
