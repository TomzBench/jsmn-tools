"""Python type-stub (.pyi) backend.

Consumes the language-neutral IR (output of flatten + sort_declarations) and
emits Python type definitions. Types only — no validators, no runtime behavior.

The type-mapping logic lives in filters (py_type / py_field / alias_rhs) that
are registered on the Jinja environment; the template owns only layout. Object
schemas (CStruct) become TypedDicts, optional fields become NotRequired[...],
and top-level string/array schemas (CArray) become type aliases. Field and type
names are kept verbatim from the spec (they are wire names).

Depends only on jsmn.ir + jsmn.primitives; nothing from the C pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader

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

_PY_PRIMITIVE: dict[Primitive, str] = {
    Primitive.UINT8: "int",
    Primitive.INT8: "int",
    Primitive.UINT16: "int",
    Primitive.INT16: "int",
    Primitive.UINT32: "int",
    Primitive.INT32: "int",
    Primitive.UINT64: "int",
    Primitive.INT64: "int",
    Primitive.FLOAT: "float",
    Primitive.DOUBLE: "float",
    Primitive.BOOL: "bool",
    Primitive.CHAR: "str",
}

_BARE_CHAR = CType("char")


def py_type(ctype: CType) -> str:
    """Map a CType to a Python type annotation.

    Leaf type comes from the primitive map (a char string buffer collapses to
    ``str``); each array dimension wraps the annotation in one ``list[...]``.
    """
    groups = ctype.dim_groups()  # inner -> outer
    wraps = 0
    if ctype.is_string:
        # Innermost group is a StringDim: its last dim is the char buffer, any
        # preceding dims are array nesting (e.g. char[4][17] -> list[str]).
        leaf = "str"
        wraps += len(groups[0].dims) - 1
        groups = groups[1:]
    elif ctype.is_primitive:
        leaf = _PY_PRIMITIVE[Primitive(ctype.name)]
    elif ctype.name == "null":
        leaf = "None"
    else:
        leaf = ctype.name  # struct / array reference
    for group in groups:
        wraps += len(group.dims) if isinstance(group, FixedDims) else 1
    ann = leaf
    for _ in range(wraps):
        ann = f"list[{ann}]"
    return ann


def py_field(field: Field) -> str:
    """Field annotation; wraps NotRequired[...] if optional."""
    if not isinstance(field.ctype, CType):
        raise NotImplementedError("unions not supported in python models yet")
    ann = py_type(field.ctype)
    return ann if field.required else f"NotRequired[{ann}]"


def alias_rhs(arr: CArray) -> str:
    """Right-hand side of a top-level array/string type alias."""
    if arr.elem == _BARE_CHAR:  # top-level string (buffer carried in min/max)
        return "str"
    return f"list[{py_type(arr.elem)}]"


def filters() -> dict[str, Callable[..., str]]:
    return {"py_type": py_type, "py_field": py_field, "alias_rhs": alias_rhs}


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
    """Render dependency-ordered IR declarations to a Python ``.pyi`` stub."""
    structs = [d for d in decls if isinstance(d, CStruct)]
    aliases = [d for d in decls if isinstance(d, CArray)]
    unknown = [d for d in decls if not isinstance(d, (CStruct, CArray))]
    if unknown:
        raise NotImplementedError(
            f"unsupported declaration: {type(unknown[0]).__name__}"
        )
    # Structs render before aliases so an alias RHS (e.g. list[point]) refers to
    # a type already defined above.
    uses_notrequired = any(not f.required for s in structs for f in s.fields)
    template = _environment().get_template("models.pyi.jinja")
    return template.render(
        structs=structs,
        aliases=aliases,
        uses_notrequired=uses_notrequired,
    )
