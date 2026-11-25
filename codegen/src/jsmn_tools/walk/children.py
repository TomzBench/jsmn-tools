"""The descent rule every crawler of a spec tree shares."""

from collections.abc import Iterator
from typing import Any, NamedTuple

from jsmn_tools.node import Behavior, Location, Node

type Context = tuple[Node[Any], Behavior]


class Child(NamedTuple):
    value: Any
    context: Context
    location: Location


def entries(
    obj: dict[str, Any],
    context: Context,
    loc: Location,
) -> Iterator[tuple[str, Child]]:
    """A key is a transition: each value gets the context its key leads to.

    That is the whole rule, for a list too: its index is its key.
    """
    (node, _) = context
    for key, val in obj.items():
        yield key, Child(val, node.child(key), loc.push(key))


def items(obj: list[Any], context: Context, loc: Location) -> Iterator[Child]:
    """The entries of a list, without the keys: an index names no one."""
    (node, _) = context
    for i, val in enumerate(obj):
        key = str(i)
        yield Child(val, node.child(key), loc.push(key))


def children(obj: Any, context: Context, loc: Location) -> Iterator[Child]:
    """The children of *obj*, whichever container it is; none for a leaf."""
    match obj:
        case dict():
            for _, child in entries(obj, context, loc):
                yield child
        case list():
            yield from items(obj, context, loc)


def is_ref(key: str, val: Any, context: Context) -> bool:
    """Whether the entry ``key: val`` of a dict at *context* is a reference.

    A ``$ref`` inside data is data. One whose value is not a string is an
    entry like any other: in a map the keys are names, so ``$ref`` may be
    one (a property called ``$ref``), and its value is then a schema.
    """
    # Decided by the value, not the node. This breaks if a draft ever gets a
    # map whose values are strings: an entry named ``$ref`` there would be
    # taken for a reference. No draft has one; maps hold objects or lists.
    (node, _) = context
    return key == "$ref" and not node.opaque and isinstance(val, str)
