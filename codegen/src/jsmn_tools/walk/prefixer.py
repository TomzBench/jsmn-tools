from typing import Any

from jsmn_tools.node import ROOT, Behavior, Location, Node, ObjectNode


def prefixer[E: str](
    obj: dict[str, Any],
    *,
    draft: ObjectNode[E],
    prefix: str,
) -> dict[str, Any]:
    """Prepend *prefix* to every ``x-jsmn-type`` value and stamp
    ``x-jsmn-prefix`` on the same schema node.

    The transform is idempotent: values that already start with *prefix*
    are left unchanged.  An empty *prefix* is a no-op.
    """
    if not prefix:
        return obj
    root = (draft, Behavior())
    return _prefixer(obj, root, ROOT, prefix=prefix)


def _prefixer(
    obj: Any,
    context: tuple[Node, Behavior],
    loc: Location,
    *,
    prefix: str,
) -> Any:
    (node, _) = context
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            out[key] = _prefixer(
                val, node.child(key), loc.push(key), prefix=prefix
            )
        if "x-jsmn-type" in out:
            original = out["x-jsmn-type"]
            if isinstance(original, str) and not original.startswith(prefix):
                out["x-jsmn-type"] = prefix + original
                out["x-jsmn-prefix"] = prefix
        return out
    if isinstance(obj, list):
        return [
            _prefixer(item, context, loc.push(str(i)), prefix=prefix)
            for i, item in enumerate(obj)
        ]
    return obj
