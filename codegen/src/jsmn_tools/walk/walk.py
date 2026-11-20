from collections.abc import Iterator
from typing import Any, NamedTuple

from jsmn_tools.node import ROOT, Behavior, Location, ObjectNode

from .children import Context, children


class Step[K: str](NamedTuple):
    value: Any
    kind: K
    location: Location


def walk[K: str](*args: Any, draft: ObjectNode[K]) -> Iterator[Step[K]]:
    """Yield (value, kind, location) for each spec tree."""
    root = (draft, Behavior())
    for obj in args:
        loc = Location.from_segments(obj["$id"]) if "$id" in obj else ROOT
        yield from _walk(obj, root, loc)


def _walk(obj: Any, context: Context, loc: Location) -> Iterator[Step[Any]]:
    (node, _) = context
    yield Step(obj, node.kind, loc)
    for child in children(obj, context, loc):
        yield from _walk(*child)
