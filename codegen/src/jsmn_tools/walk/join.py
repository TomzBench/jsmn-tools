# Join = merge every spec into one document, remembering who clashed

from dataclasses import dataclass
from typing import Any

from jsmn_tools.node import Behavior, Location, ObjectNode

from .merge import merge


@dataclass
class JoinConflict:
    """Two specs defined one thing differently.

    Both locations are fully resolved: the spec's ``$id``, then the path
    inside it. ``destination`` is the definition the join kept, ``source``
    the one it rejected.
    """

    destination: Location
    source: Location


@dataclass
class JoinResult:
    value: Any
    conflicts: list[JoinConflict]


def join[E: str](*specs: dict, draft: ObjectNode[E]) -> JoinResult:
    """Merge *specs* into one document

    Args:
        specs:  A normalized spec with an ``$id`` prop in the root

    Returns:
        JoinResult: The joined spec and array of `JoinConflict`s found
    """
    dest: Any = {}  # merged result
    conflicts: list[JoinConflict] = []  # collected conflicts
    seen: dict[str, Any] = {}  # cache of already seen $id's and their docs
    root = (draft, Behavior())

    for spec in specs:
        id = spec["$id"]
        if id in seen:
            raise ValueError(f"join: $id used by two specs: {id}")
        seen |= {id: spec}
        # must strip $id or we guarentee $id will merge conflict on n+1
        doc = {k: v for k, v in spec.items() if k != "$id"}
        (dest, merge_conflicts) = merge(dest, doc, root)
        for c in merge_conflicts:
            conflict_location = next(
                id for id, doc in seen.items() if c.location.exists(doc)
            )
            destination = Location((conflict_location, *c.location))
            source = Location((id, *c.location))
            conflicts.append(JoinConflict(destination, source))
    return JoinResult(dest, conflicts)
