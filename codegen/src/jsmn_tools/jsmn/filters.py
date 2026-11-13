from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from referencing.exceptions import Unresolvable

from jsmn_tools.node import Location

from .descriptor import (
    ArrayDescriptor,
    ArrayKind,
    Descriptor,
    Descriptors,
    FieldDescriptor,
    Key,
    StructDescriptor,
    Table,
)
from .ir import (
    CArray,
    CDecl,
    CEnum,
    CStruct,
    CType,
    CUnion,
    Dim,
    Variant,
)
from .primitives import Primitive

if TYPE_CHECKING:
    from collections.abc import Callable

    from referencing._core import Resolver


class ShimMode(StrEnum):
    NONE = "none"
    EXTERN = "extern"
    INLINE = "inline"


# ── General-purpose filters ──────────────────────────────────────────


def snake_case(s: str, shouty: bool = False) -> str:
    """Convert to snake_case. shouty=True gives UPPER_SNAKE_CASE."""
    result = re.sub(r"(?<!^)(?=[A-Z])", "_", s).replace("-", "_")
    return result.upper() if shouty else result.lower()


def camel_case(s: str, upper: bool = False) -> str:
    """Convert to camelCase. upper=True gives PascalCase."""
    result = re.sub(r"[_-]", " ", snake_case(s)).title().replace(" ", "")
    return (
        result[0].upper() + result[1:]
        if upper
        else result[0].lower() + result[1:]
    )


# ── Rendering maps ────────────────────────────────────────────────────

_PRIM_KINDS: dict[Primitive, str] = {
    Primitive.BOOL: "JT_KIND_BOOL",
    Primitive.CHAR: "JT_KIND_CHAR",
    Primitive.UINT8: "JT_KIND_U8",
    Primitive.INT8: "JT_KIND_I8",
    Primitive.UINT16: "JT_KIND_U16",
    Primitive.INT16: "JT_KIND_I16",
    Primitive.UINT32: "JT_KIND_U32",
    Primitive.INT32: "JT_KIND_I32",
    Primitive.UINT64: "JT_KIND_U64",
    Primitive.INT64: "JT_KIND_I64",
    Primitive.FLOAT: "JT_KIND_FLOAT",
    Primitive.DOUBLE: "JT_KIND_DOUBLE",
}
assert _PRIM_KINDS.keys() == set(Primitive), "missing primitive kind"

_ARRAY_KINDS: dict[ArrayKind, str] = {
    ArrayKind.FIXED: "JT_KIND_FIXED",
    ArrayKind.STRING: "JT_KIND_STRING",
    ArrayKind.VLA: "JT_KIND_VLA",
}


def tests(
    user_decls: list[CDecl],
    resolver: Resolver,
) -> dict[str, Callable[..., Any]]:
    cdecl_index = {v.ctype.name: v for v in user_decls}
    array_names = {v.ctype.name for v in user_decls if isinstance(v, CArray)}

    def is_struct_decl(decl: CDecl) -> bool:
        return isinstance(decl, CStruct)

    def is_union_decl(decl: CDecl) -> bool:
        return isinstance(decl, CUnion)

    def is_enum_decl(decl: CDecl) -> bool:
        return isinstance(decl, CEnum)

    def is_array_decl(decl: CDecl | CType) -> bool:
        name = decl.name if isinstance(decl, CType) else decl.ctype.name
        return name in array_names

    def is_user_decl(decl: CDecl | CType) -> bool:
        t = decl.name if isinstance(decl, CType) else decl.ctype.name
        return t in cdecl_index

    def is_union_ctype(ctype: CType | tuple[Variant, ...]) -> bool:
        return not isinstance(ctype, CType)

    def is_public(d: Descriptors) -> bool:
        if isinstance(d, StructDescriptor):
            return True
        if isinstance(d, ArrayDescriptor):
            return d.ctype.name in array_names
        return False

    # Tag lookup is a single resolver hit — no recursion. The decl's
    # location points to the schema where x-jsmn-type was found,
    # and x-jsmn-tag must be co-located on that same schema. Tags on
    # $ref targets or allOf branches are not inherited. A future
    # validation pass could warn when x-jsmn-tag appears on a schema
    # without x-jsmn-type (misplaced tag).
    def is_tagged(decl: CDecl, tag: str) -> bool:
        try:
            spec_id = decl.loc[0]
            resolved = resolver.lookup(spec_id)
            path = type(decl.loc)(decl.loc[1:])
            schema = path.resolve(resolved.contents)
            tags = schema.get("x-jsmn-tag", [])
            if isinstance(tags, str):
                tags = [tags]
            return tag in tags
        except LookupError:
            return False

    return {
        "struct_decl": is_struct_decl,
        "union_decl": is_union_decl,
        "enum_decl": is_enum_decl,
        "array_decl": is_array_decl,
        "user_decl": is_user_decl,
        "union_ctype": is_union_ctype,
        "tagged": is_tagged,
        "public": is_public,
    }


def filters(
    table: dict[Key, Descriptors],
    decls: list[CDecl],
    resolver: Resolver,
) -> dict[str, Callable[..., Any]]:
    """Return all template filters (stateless + table-rendering closures)."""
    # ── Build index for positional lookups ──────────────────────────
    struct_index: dict[str, int] = {
        d.ctype.name: d.key.pos
        for d in table.values()
        if isinstance(d, StructDescriptor)
    }
    array_index: dict[str, int] = {
        d.ctype.name: d.key.pos
        for d in table.values()
        if isinstance(d, ArrayDescriptor)
    }

    cdecl_index = {v.ctype.name: v for v in decls}
    # NOTE FieldDescriptors are excluded — a required struct-typed field
    # shares its resolved CType with the struct's own StructDescriptor,
    # so including fields would create key collisions that resolve to the
    # wrong schema location. If per-field descriptor lookup is needed,
    # use a composite key: (parent CType, field name).
    #
    #   field_index = {
    #       (table[d.parent].ctype, d.name): d
    #       for d in table.values()
    #       if isinstance(d, FieldDescriptor)
    #   }
    descriptor_index: dict[CType, StructDescriptor | ArrayDescriptor] = {
        d.ctype: d
        for d in table.values()
        if isinstance(d, (StructDescriptor, ArrayDescriptor))
    }

    def qualifier(ctype: CType) -> str:
        qual = cdecl_index.get(ctype.name)
        if qual is None:
            return ""
        elif isinstance(qual, CUnion):
            return "union"
        elif isinstance(qual, CArray):
            return ""
        else:
            return "struct"

    def raw(ctype: CType) -> CType:
        """Spell a named fixed array as its element type and count."""
        d = cdecl_index.get(ctype.name)
        if isinstance(d, CArray) and d.min == d.max:
            return CType(
                d.elem.name, (Dim(d.max, d.max), *d.elem.dims, *ctype.dims)
            )
        return ctype

    def _resolve_ctype(ctype: CType) -> str:
        if ctype.name in Primitive:
            return f"JT_PRIM({_PRIM_KINDS[Primitive(ctype.name)]})"
        elif ctype.name in struct_index:
            return f"JT_STRUCT({struct_index[ctype.name]})"
        elif ctype.name in array_index:
            return f"JT_ARRAY({array_index[ctype.name]})"
        else:
            raise ValueError(f"{ctype.name} not indexable")

    def _resolve_ref(ref: Key | CType) -> str:
        if isinstance(ref, CType):
            return _resolve_ctype(ref)
        return f"JT_ARRAY({ref.pos})"

    def dimensions(dims: tuple[Dim, ...]) -> str:
        return "".join(f"[{d.max}]" for d in dims)

    # ── Table-rendering closures ──────────────────────────────────────

    def name_offset(f: FieldDescriptor) -> str:
        return str(f.name_offset)

    def _rename_field(name: str, parent: Descriptor) -> str:
        """Apply x-jsmn-rename / x-jsmn-rename-all for offsetof expressions."""
        if rename := location(parent, "properties", name, "x-jsmn-rename"):
            return rename
        elif rename := location(parent, "x-jsmn-rename-all"):
            return caseify(name, rename)
        else:
            return name

    def value_offset(f: FieldDescriptor) -> str:
        parent = table[f.parent]
        c_name = _rename_field(f.name, parent)
        base = f"offsetof(struct {parent.ctype.name}, {c_name})"
        if f.optional:
            return f"{base} + offsetof(struct {f.ctype.name}, maybe)"
        return base

    def present_offset(f: FieldDescriptor) -> str:
        if not f.optional:
            return "0xFFFF"
        parent = table[f.parent]
        c_name = _rename_field(f.name, parent)
        return f"offsetof(struct {parent.ctype.name}, {c_name})"

    def size_expr(s: StructDescriptor) -> str:
        return f"sizeof(struct {s.ctype.name})"

    def type_expr(f: FieldDescriptor) -> str:
        return _resolve_ref(f.type_ref)

    def elem_expr(a: ArrayDescriptor) -> str:
        return _resolve_ref(a.elem)

    def elem_size(a: ArrayDescriptor) -> str:
        if isinstance(a.elem, CType):
            if a.elem.name in Primitive:
                return f"sizeof({a.elem.name})"
            if not isinstance(cdecl_index.get(a.elem.name), CArray):
                return f"sizeof(struct {a.elem.name})"
            child = table[Key(Table.ARRAY, array_index[a.elem.name])]
        else:
            child = table[a.elem]
        assert isinstance(child, ArrayDescriptor)
        if child.kind in (ArrayKind.FIXED, ArrayKind.STRING):
            return "0"
        # VLA child — stride is the wrapper struct size
        return f"sizeof(struct {child.ctype.name})"

    def array_kind(a: ArrayDescriptor) -> str:
        return _ARRAY_KINDS[a.kind]

    # ── Comment filter ─────────────────────────────────────────────────

    def comment(d: Descriptors) -> str:
        loc = d.loc.to_pointer()
        if isinstance(d, StructDescriptor):
            return f"{d.ctype.name} @ {loc}"
        elif isinstance(d, FieldDescriptor):
            parent = table[d.parent]
            opt = " (optional)" if d.optional else ""
            return f"{parent.ctype.name}.{d.name}{opt} @ {loc}"
        else:
            return f"{d.kind.name.lower()} {d.ctype.name} max={d.max} @ {loc}"

    # ── Descriptor-list filters (used in template iteration) ─────────

    def structs(ds: list[Descriptors]) -> list[StructDescriptor]:
        return [d for d in ds if isinstance(d, StructDescriptor)]

    def fields(ds: list[Descriptors]) -> list[FieldDescriptor]:
        return [d for d in ds if isinstance(d, FieldDescriptor)]

    def arrays(ds: list[Descriptors]) -> list[ArrayDescriptor]:
        return [d for d in ds if isinstance(d, ArrayDescriptor)]

    def table_kind(d: Descriptors) -> str | None:
        if isinstance(d, StructDescriptor):
            return "JT_STRUCT"
        if isinstance(d, ArrayDescriptor):
            return "JT_ARRAY"
        return None

    # ── Document-aware schema filters ────────────────────────────────────

    def location(obj: CDecl | Descriptor, *segments: str) -> Any | None:
        if isinstance(obj, Descriptor):
            base = obj.loc
        elif desc := descriptor_index.get(obj.ctype):
            base = desc.loc
        else:
            return None

        try:
            root = resolver.lookup(base[0])
        except Unresolvable:
            return None
        return Location.from_segments(*base[1:], *segments).get(root.contents)

    def _lookup_prefix(obj: Any) -> str:
        return location(obj, "x-jsmn-prefix") or ""

    def type_prefix(decl: Any) -> str:
        return _lookup_prefix(decl)

    def type_prefix_or(decl: Any, fallback: str = "") -> str:
        return _lookup_prefix(decl) or fallback

    def nameify(decl: Any) -> str:
        pfx = _lookup_prefix(decl)
        return decl.ctype.name[len(pfx) :]

    def method_name(decl: Any, method: str, fallback_prefix: str = "") -> str:
        pfx = _lookup_prefix(decl) or fallback_prefix
        return f"{pfx}{method}_{nameify(decl)}"

    def shim_mode_or(decl: Any, fallback: ShimMode) -> ShimMode:
        raw = location(decl, "x-jsmn-shim")
        if raw is None:
            return fallback
        return ShimMode(raw)

    _RENAME_FNS: dict[str, Callable[[str], str]] = {
        "snake_case": snake_case,
    }

    def caseify(name: str, rule: str) -> str:
        fn = _RENAME_FNS.get(rule)
        return fn(name) if fn else name

    # ── JSON pointer filter (resolve $ref via resolver) ───────────────

    def json_pointer(ref: str, base: str | None = None) -> Any:
        """Resolve *ref*. A fragment-only ref needs *base*: its document's
        ``$id``."""
        scoped = resolver.lookup(base).resolver if base else resolver
        return scoped.lookup(ref).contents

    result: dict[str, Callable[..., Any]] = {
        "dimensions": dimensions,
        "comment": comment,
        "name_offset": name_offset,
        "value_offset": value_offset,
        "present_offset": present_offset,
        "size_expr": size_expr,
        "type_expr": type_expr,
        "elem_expr": elem_expr,
        "elem_size": elem_size,
        "array_kind": array_kind,
        "structs": structs,
        "fields": fields,
        "arrays": arrays,
        "table_kind": table_kind,
        "qualifier": qualifier,
        "raw": raw,
        "snake_case": snake_case,
        "camel_case": camel_case,
        "json_pointer": json_pointer,
        "type_prefix": type_prefix,
        "type_prefix_or": type_prefix_or,
        "nameify": nameify,
        "method_name": method_name,
        "shim_mode_or": shim_mode_or,
        "location": location,
        "caseify": caseify,
    }

    return result
