"""TypeScript declaration (.d.ts) backend.

Consumes the language-neutral IR (output of flatten + sort_declarations) and
emits TypeScript type definitions. Types only — no validators, no runtime
behavior.

Object schemas (CStruct) become `export interface`s with `?` on optional
fields; top-level string/array schemas (CArray) become `export type` aliases.
Type identifiers are UpperCamelCased (a TS convention) via camel_case; the same
transform is applied at declarations and references, so they stay consistent.
Property names are kept verbatim — they are the JSON wire keys. All numeric
widths map to `number` (lossy for 64-bit, but matches what JSON.parse yields).

The type-mapping logic lives in filters (ts_type / ts_member / alias_rhs);
the template owns only layout. Depends only on jsmn.ir + jsmn.primitives +
the generic camel_case helper; nothing from the C pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader

from jsmn_tools.jsmn.filters import camel_case
from jsmn_tools.jsmn.ir import (
    CArray,
    CDecl,
    CStruct,
    CType,
    Field,
    FixedDims,
)
from jsmn_tools.jsmn.primitives import Primitive

if TYPE_CHECKING:
    from collections.abc import Callable

_TS_PRIMITIVE: dict[Primitive, str] = {
    Primitive.UINT8: "number",
    Primitive.INT8: "number",
    Primitive.UINT16: "number",
    Primitive.INT16: "number",
    Primitive.UINT32: "number",
    Primitive.INT32: "number",
    Primitive.UINT64: "number",
    Primitive.INT64: "number",
    Primitive.FLOAT: "number",
    Primitive.DOUBLE: "number",
    Primitive.BOOL: "boolean",
    Primitive.CHAR: "string",
}

_BARE_CHAR = CType("char")


def ts_type(ctype: CType) -> str:
    """Map a CType to a TypeScript type.

    Leaf comes from the primitive map (a char string buffer collapses to
    ``string``); a struct/array reference is UpperCamelCased; each array
    dimension appends one ``[]`` (e.g. number[][], Point[], string[]).
    """
    groups = ctype.dim_groups()  # inner -> outer
    wraps = 0
    if ctype.is_string:
        # Innermost group is a StringDim: its last dim is the char buffer, any
        # preceding dims are array nesting (e.g. char[4][17] -> string[]).
        leaf = "string"
        wraps += len(groups[0].dims) - 1
        groups = groups[1:]
    elif ctype.is_primitive:
        leaf = _TS_PRIMITIVE[Primitive(ctype.name)]
    elif ctype.name == "null":
        leaf = "null"
    else:
        leaf = camel_case(ctype.name, upper=True)  # struct / array reference
    for group in groups:
        wraps += len(group.dims) if isinstance(group, FixedDims) else 1
    ann = leaf
    for _ in range(wraps):
        ann = f"{ann}[]"
    return ann


def ts_member(field: Field) -> str:
    """Interface member `name: type` (`name?:` if optional); name verbatim."""
    if not isinstance(field.ctype, CType):
        raise NotImplementedError(
            "unions not supported in typescript models yet"
        )
    opt = "" if field.required else "?"
    return f"{field.name}{opt}: {ts_type(field.ctype)}"


def alias_rhs(arr: CArray) -> str:
    """Right-hand side of a top-level array/string type alias."""
    if arr.elem == _BARE_CHAR:  # top-level string (buffer carried in min/max)
        return "string"
    return f"{ts_type(arr.elem)}[]"


def filters() -> dict[str, Callable[..., str]]:
    return {
        "ts_type": ts_type,
        "ts_member": ts_member,
        "alias_rhs": alias_rhs,
        "camel_case": camel_case,
    }


def _environment() -> Environment:
    env = Environment(
        loader=PackageLoader("jsmn_tools", "lang/templates"),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(filters())
    return env


def render_models(decls: list[CDecl]) -> str:
    """Render dependency-ordered IR declarations to a TypeScript ``.d.ts``."""
    structs = [d for d in decls if isinstance(d, CStruct)]
    aliases = [d for d in decls if isinstance(d, CArray)]
    unknown = [d for d in decls if not isinstance(d, (CStruct, CArray))]
    if unknown:
        raise NotImplementedError(
            f"unsupported declaration: {type(unknown[0]).__name__}"
        )
    # Structs render before aliases so an alias RHS (e.g. Point[]) refers to a
    # type already declared above.
    template = _environment().get_template("models.d.ts.jinja")
    return template.render(structs=structs, aliases=aliases)
