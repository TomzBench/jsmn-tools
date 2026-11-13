from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, NamedTuple

from jsmn_tools.node import ROOT, Behavior, Location, Node


@dataclass
class MergeConflict:
    location: Location
    destination: Any
    source: Any


class MergeResult(NamedTuple):
    value: Any
    conflicts: list[MergeConflict]


def _leaf(
    dst: Any,
    src: Any,
    loc: Location,
    conflicts: list[MergeConflict],
) -> Any:
    """Compare two values whole; a difference is a conflict, and the
    destination is kept."""
    if dst != src:
        conflicts.append(MergeConflict(loc, dst, src))
    return dst


def _merge_dict(
    dst: dict[str, Any],
    src: dict[str, Any],
    context: tuple[Node, Behavior],
    loc: Location,
    conflicts: list[MergeConflict],
) -> dict[str, Any]:
    """Key by key; the entries of an identified dict are compared whole."""
    (node, behavior) = context
    identity = behavior.identity
    result = dict(dst)
    # An identified dict pairs its entries by identity(key), not by key.
    # Every draft uses str today, which leaves the key as it is; the lookup
    # is here so an identity that folds keys (case, say) pairs them too.
    names = {identity(k): k for k in result} if identity else {}
    for key, v in src.items():
        k = names.setdefault(identity(key), key) if identity else key
        at = loc.push(k)
        if k not in result:
            result[k] = deepcopy(v)
        elif identity:
            result[k] = _leaf(result[k], v, at, conflicts)
        else:
            result[k] = _merge(result[k], v, node.child(k), at, conflicts)
    return result


def _merge_list(
    dst: list[Any],
    src: list[Any],
    context: tuple[Node, Behavior],
    loc: Location,
    conflicts: list[MergeConflict],
) -> list[Any]:
    """Position by position; the items of an identified list are paired by
    identity, compared whole, and kept sorted."""
    (_, behavior) = context
    if identity := behavior.identity:
        seen = {identity(x): x for x in dst}
        for item in src:
            k = identity(item)
            if k not in seen:
                seen[k] = deepcopy(item)
            else:
                # an item has no pointer of its own: located at the list
                seen[k] = _leaf(seen[k], item, loc, conflicts)
        return sorted(seen.values(), key=identity)
    merged = [
        _merge(a, b, context, loc.push(str(i)), conflicts)
        for i, (a, b) in enumerate(zip(dst, src, strict=False))
    ]
    return merged + [deepcopy(x) for x in src[len(dst) :]]


def _merge(
    dst: Any,
    src: Any,
    context: tuple[Node, Behavior],
    loc: Location,
    conflicts: list[MergeConflict],
) -> Any:
    if isinstance(dst, dict) and isinstance(src, dict):
        return _merge_dict(dst, src, context, loc, conflicts)
    if isinstance(dst, list) and isinstance(src, list):
        return _merge_list(dst, src, context, loc, conflicts)
    return _leaf(dst, src, loc, conflicts)


def merge(
    dst: Any,
    src: Any,
    context: tuple[Node, Behavior],
    loc: Location = ROOT,
) -> MergeResult:
    """Merge *src* into a copy of *dst*; neither argument is changed."""
    conflicts: list[MergeConflict] = []
    value = _merge(dst, src, context, loc, conflicts)
    return MergeResult(value, conflicts)
