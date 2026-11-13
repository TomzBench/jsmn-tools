"""What a bundle tells the user: join conflicts and dangling refs.

Everything here is presentation. The walks report plainly (a conflict is
two locations, a dangling ref is one); this module decides what to say
about them and prints it to stderr.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from jsmn_tools.node import Behavior, Location, Node, ObjectNode
from jsmn_tools.spec import ConflictRules, Verdict
from jsmn_tools.walk import JoinConflict, dangling

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

type Context = tuple[Node, Behavior]


def _show(path: Sequence[str]) -> str:
    """Display segments as a pointer-like string.

    Not a JSON pointer: an item of an identified list is shown by its
    identity (``/parameters/query,limit``), which no document can resolve.
    """
    return Location(path).to_pointer()


def _context(doc: Any, path: Location, context: Context) -> Context:
    """The draft's node and behavior for the value at *path* in *doc*."""
    for key in path:
        if isinstance(doc, dict):
            context = context[0].child(key)
        doc = Location((key,)).resolve(doc)
    return context


def _differences(
    a: Any,
    b: Any,
    context: Context,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], str]]:
    """Where *b* differs from *a*: (display path, what differs).

    What differs is ``<``, only in *a*; ``>``, only in *b*; or the two
    values. A list whose items the draft identifies is compared by
    identity, so one extra item reads as one difference and not as every
    later position mismatching.
    """
    (node, behavior) = context
    if isinstance(a, dict) and isinstance(b, dict):
        for k in (*a, *(k for k in b if k not in a)):
            at = (*path, k)
            if k not in b:
                yield (at, "<")
            elif k not in a:
                yield (at, ">")
            else:
                yield from _differences(a[k], b[k], node.child(k), at)
    elif isinstance(a, list) and isinstance(b, list):
        ia = _keyed(a, behavior)
        ib = _keyed(b, behavior)
        for k in (*ia, *(k for k in ib if k not in ia)):
            at = (*path, k.replace("\x00", ","))
            if k not in ib:
                yield (at, "<")
            elif k not in ia:
                yield (at, ">")
            else:
                yield from _differences(ia[k], ib[k], context, at)
    elif a != b:
        (x, y) = (_json(a), _json(b))
        yield (path, f"{x} != {y}")


def _keyed(items: list[Any], behavior: Behavior) -> dict[str, Any]:
    """Items by identity, or by position when the list has none."""
    if identity := behavior.identity:
        return {identity(x): x for x in items}
    return {str(i): x for i, x in enumerate(items)}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def explain[E: str](
    conflict: JoinConflict,
    specs: Mapping[str, Any],
    draft: ObjectNode[E],
    limit: int | None = None,
) -> list[str]:
    """One line naming both sides, then one line per difference.

    *specs* are the join's inputs by ``$id``. ``limit`` caps the difference
    lines; None prints every one.
    """
    (kept, *path) = conflict.destination
    (rejected, *_) = conflict.source
    where = Location(path)
    context = _context(specs[kept], where, (draft, Behavior()))
    (a, b) = (where.resolve(specs[kept]), where.resolve(specs[rejected]))
    names = {"<": f"only in {kept}", ">": f"only in {rejected}"}
    details = [
        f"  {_show(at)}: {names.get(what, what)}" if at else f"  {what}"
        for at, what in _differences(a, b, context)
    ]
    shown = details if limit is None else details[:limit]
    pointer = where.to_pointer()
    lines = [f"{kept}#{pointer} vs {rejected}#{pointer}", *shown]
    if len(shown) < len(details):
        lines.append(f"  ... {len(details) - len(shown)} more")
    return lines


def report_conflicts[E: str](
    conflicts: Sequence[JoinConflict],
    specs: Mapping[str, Any],
    draft: ObjectNode[E],
    rules: ConflictRules,
    mode: str = "warn",
    limit: int | None = None,
) -> bool:
    """Print every conflict the rules do not ignore; True if any must fail.

    *mode* ``warn`` reports an error as a warning. Two conflicts between the
    same pair of locations are one report: it lists every difference.
    """
    failed = False
    seen: set[tuple[Location, Location]] = set()
    for c in conflicts:
        verdict = rules(Location(c.source[1:]))
        if verdict is Verdict.IGNORE or (c.destination, c.source) in seen:
            continue
        seen.add((c.destination, c.source))
        if verdict is Verdict.ERROR and mode == "warn":
            verdict = Verdict.WARN
        failed = failed or verdict is Verdict.ERROR
        (head, *rest) = explain(c, specs, draft, limit)
        print(f"{verdict.value}: conflict: {head}", file=sys.stderr)
        for line in rest:
            print(line, file=sys.stderr)
    return failed


def report_dangling[E: str](doc: Any, draft: ObjectNode[E], name: str) -> None:
    """Warn of every local $ref in *doc* that points at nothing."""
    for d in dangling(doc, draft):
        at = d.location.to_pointer()
        print(f"warning: dangling $ref: {name}#{at}: {d.ref}", file=sys.stderr)
