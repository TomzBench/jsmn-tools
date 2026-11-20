from typing import Any

from jsmn_tools.node import ROOT, Location, Ref, SchemeURI

from .children import Context, entries, is_ref, items


# TODO cache anchors and strip duplicates
def normalize(
    obj: dict[str, Any],
    context: Context,
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


def _normalize(obj: Any, context: Context, loc: Location) -> Any:
    (_, behavior) = context
    match obj:
        case dict():
            out: dict[str, Any] = {}
            for key, child in entries(obj, context, loc):
                if is_ref(key, child.value, context):
                    out[key] = collapse_ref(child.value)
                else:
                    out[key] = _normalize(*child)
            return out
        case list():
            identity = behavior.identity
            normalized = [_normalize(*c) for c in items(obj, context, loc)]
            return sorted(normalized, key=identity) if identity else normalized
        case _:
            return obj
