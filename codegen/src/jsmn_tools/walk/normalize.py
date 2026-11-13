from typing import Any

from jsmn_tools.node import ROOT, Behavior, Location, Node, Ref, SchemeURI


# TODO cache anchors and strip duplicates
def normalize(
    obj: dict[str, Any],
    context: tuple[Node, Behavior],
    loc: Location = ROOT,
) -> dict[str, Any]:
    return _normalize(obj, context, loc)


def collapse_ref(raw: str) -> str:
    """Point a ref at the joined document.

    A join puts every input in one document, so a ref into another input
    (``./sibling.yaml#/x`` or ``scheme://module/name/vN#/x``) becomes the
    local ``#/x``. Refs with nothing to point at inside the document are
    left as written: no fragment, or an http(s)/file URI.
    """
    ref = Ref(raw)
    if ref.is_local or ref.fragment is None:
        return raw
    if ref.is_relative:
        return f"#{ref.fragment}"
    uri = SchemeURI.parse(raw)
    if uri and not uri.is_passthrough:
        return f"#{ref.fragment}"
    return raw


def _normalize(
    obj: Any,
    context: tuple[Node, Behavior],
    loc: Location,
) -> Any:
    (node, behavior) = context
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if key == "$ref" and not node.opaque:
                out[key] = collapse_ref(val) if isinstance(val, str) else val
            else:
                out[key] = _normalize(val, node.child(key), loc.push(key))
        return out
    if isinstance(obj, list):
        identity = behavior.identity
        items = [
            _normalize(item, context, loc.push(str(i)))
            for i, item in enumerate(obj)
        ]
        return sorted(items, key=identity) if identity else items
    return obj
