from typing import Any

from jsmn_tools.node import ROOT, Behavior, Location, ObjectNode

from .children import Context, entries, items


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
    context: Context,
    loc: Location,
    *,
    prefix: str,
) -> Any:
    match obj:
        case dict():
            out: dict[str, Any] = {
                key: _prefixer(*child, prefix=prefix)
                for key, child in entries(obj, context, loc)
            }
            # Known and accepted: also stamps an x-jsmn-type found in data
            # (default, example, x-*). Gating on schema nodes would instead
            # miss a $ref target outside the draft's schema positions: worse.
            if "x-jsmn-type" in out:
                original = out["x-jsmn-type"]
                if isinstance(original, str) and not original.startswith(
                    prefix
                ):
                    out["x-jsmn-type"] = prefix + original
                    out["x-jsmn-prefix"] = prefix
            return out
        case list():
            return [
                _prefixer(*child, prefix=prefix)
                for child in items(obj, context, loc)
            ]
        case _:
            return obj
