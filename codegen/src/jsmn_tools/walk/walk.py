from collections.abc import Iterator
from typing import Any, NamedTuple

from jsmn_tools.node import ROOT, Behavior, Location, Node, ObjectNode


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


def _walk(
    obj: Any,
    context: tuple[Node[Any], Behavior],
    loc: Location,
) -> Iterator[Step[Any]]:
    (node, _) = context
    yield Step(obj, node.kind, loc)
    if isinstance(obj, dict):
        for key, val in obj.items():
            yield from _walk(val, node.child(key), loc.push(key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk(item, context, loc.push(str(i)))
