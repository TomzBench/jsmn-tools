from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    DictLoader,
    Environment,
    PackageLoader,
)
from referencing import Registry

from .descriptor import (
    ArrayDescriptor,
    ArrayKind,
    Descriptors,
    FieldDescriptor,
    Key,
    Strings,
    StructDescriptor,
    Table,
    add_array_with_cache,
    sum_encode_len_with_cache,
    sum_ntoks_with_cache,
)
from .filters import ShimMode, filters, tests
from .flatten import flatten_registry
from .ir import CArray, CDecl, CStruct, CType, CUnion, Dim, Field, FixedDims
from .mangle import dim_walk, make_maybe, make_optional, make_vla, mangle

if TYPE_CHECKING:
    from collections.abc import Sequence

    from referencing._core import Resolver

    from jsmn_tools.node import Location


def resolve_ctype(ctype: CType, optional: bool = False) -> CType:
    """Collapse VLA dims into wrapper names, keep leading fixed dims."""
    inner = CType(ctype.name)
    for group in ctype.dim_groups():
        if isinstance(group, FixedDims):
            inner = CType(inner.name, group.dims)
        else:
            spec = CType(inner.name, (group, *inner.dims))
            inner = CType(mangle(spec))
    if optional:
        return CType(mangle(inner, optional=True))
    else:
        return inner


def extend_declarations(ordered: list[CDecl]) -> list[CDecl]:
    """Create synthetic wrappers and resolve field CTypes in one pass."""
    cache: set[CType] = set()
    ret: list[CDecl] = []

    def emit(d: CDecl) -> None:
        if d.ctype not in cache:
            cache.add(d.ctype)
            ret.append(d)

    for d in ordered:
        if isinstance(d, CStruct):
            fields: list[Field] = []
            for f in d.fields:
                if not isinstance(f.ctype, CType):
                    if not f.required:
                        resolved = CType(mangle(f.ctype, optional=True))
                        fields.append(Field(f.name, resolved, required=True))
                    else:
                        fields.append(f)
                else:
                    prop_loc = d.loc.push(f.name)
                    resolved = resolve_ctype(f.ctype)
                    for group, spec in dim_walk(f.ctype):
                        if not isinstance(group, FixedDims):
                            emit(make_vla(spec, prop_loc))
                    if not f.required:
                        emit(make_maybe(resolved, prop_loc))
                        emit(make_optional(resolved, prop_loc))
                        resolved = resolve_ctype(f.ctype, optional=True)
                        fields.append(Field(f.name, resolved, required=True))
                    else:
                        fields.append(Field(f.name, resolved, f.required))
            emit(CStruct(d.ctype, d.loc, fields))
        elif isinstance(d, CArray):
            if d.min != d.max:  # VLA — emit wrapper struct with user's name
                resolved_elem = resolve_ctype(d.elem)
                spec = CType(resolved_elem.name, (Dim(d.min, d.max),))
                for group, inner_spec in dim_walk(d.elem):
                    if not isinstance(group, FixedDims):
                        emit(make_vla(inner_spec, d.loc))
                emit(make_vla(spec, d.loc, name=d.ctype.name))
            else:  # Fixed — pass through as CArray for typedef rendering
                emit(d)
        elif isinstance(d, CUnion):
            emit(d)
        else:
            raise NotImplementedError
    return ret


def sort_declarations(decls: dict[CType, CDecl]) -> list[CDecl]:
    """Dependency-order user-defined decls (no synthetic wrappers)."""
    cache: set[CType] = set()
    ret: list[CDecl] = []

    def walker(curr: CDecl) -> None:
        if curr.ctype in cache:
            return
        cache.add(curr.ctype)
        if isinstance(curr, CStruct):
            for prop in curr.fields:
                if isinstance(prop.ctype, CType):
                    if prop.ctype in decls:
                        walker(decls[prop.ctype])
                else:
                    for v in prop.ctype:
                        if v.ctype in decls:
                            walker(decls[v.ctype])
            ret.append(curr)
        elif isinstance(curr, CArray):
            if curr.elem in decls:
                walker(decls[curr.elem])
            ret.append(curr)
        else:
            raise NotImplementedError

    for decl in decls.values():
        walker(decl)
    return ret


def build_tables(
    ordered: Sequence[CDecl],
) -> tuple[Strings, dict[Key, Descriptors]]:
    structs: list[StructDescriptor] = []
    fields: list[FieldDescriptor] = []
    arrays, add_array = add_array_with_cache()
    # NOTE ntoks/len summers are incorrect w/ Optional type wrappers and VLA
    #      type wrappers. Synthetic wrapper types are helpers which are
    #      not represented on the wire. For example, we represent an optional
    #      field with a "present" bit. Our current calculations assume the wire
    #      transmits the present field.
    #      To fix, mangle.py should tag the CStruct vla's as a CVla, and the
    #      Optional maybe as CMaybe, and inherit CStruct and CUnion respectively.
    #      This will behave as expected everywhere, and summers can test if its
    #      synthetic or not.
    #      These synthetic types should declare in mangle.py. The summers should
    #      Move into it's own file so no circulars. (ie: calculate.py)
    sum_ntoks = sum_ntoks_with_cache()
    sum_encode_len = sum_encode_len_with_cache()
    strings = Strings()

    def resolve_array(
        ctype: CType, loc: Location, *, name: str | None = None
    ) -> Key:
        """Walk dims inner-to-outer, creating/reusing array descriptors."""
        ref: Key | CType = CType(ctype.name)  # bare leaf
        for group, spec in dim_walk(ctype):
            kind = ArrayKind.from_group(group)
            entries = (
                [(ctype, dim.max) for dim in reversed(group.dims)]
                if isinstance(group, FixedDims)
                else [(spec, group.max)]
            )
            for ct, mx in entries:
                arr = ArrayDescriptor(
                    key=Key(Table.ARRAY, len(arrays)),
                    loc=loc,
                    ntoks=sum_ntoks(ct),
                    encode_len=sum_encode_len(ct),
                    ctype=resolve_ctype(ct),
                    kind=kind,
                    max=mx,
                    elem=ref,
                )
                ref = add_array(arr)
        assert isinstance(ref, Key)
        if name is not None:
            # Named user types need their own descriptor entry so that:
            # 1. loc points to their schema (where x-jsmn-prefix is stamped)
            #    for prefix/nameify lookups in templates.
            # 2. Two user types with the same shape don't overwrite each
            #    other — the cache would alias them to the same entry and
            #    the second rename would destroy the first type's descriptor.
            # Copy shape from the cached (possibly anonymous) descriptor but
            # give this user type its own entry with correct ctype and loc.
            cached = arrays[ref.pos]
            named = ArrayDescriptor(
                key=Key(Table.ARRAY, len(arrays)),
                loc=loc,
                ntoks=cached.ntoks,
                encode_len=cached.encode_len,
                ctype=CType(name),
                kind=cached.kind,
                max=cached.max,
                elem=cached.elem,
            )
            arrays.append(named)
        return ref

    for d in ordered:
        if isinstance(d, CStruct):
            struct_key = Key(Table.STRUCT, len(structs))
            s = StructDescriptor(
                key=struct_key,
                loc=d.loc,
                ntoks=sum_ntoks(d),
                encode_len=sum_encode_len(d),
                ctype=d.ctype,
                nfields=len(d.fields),
                field0=len(fields),
            )
            structs.append(s)
            for f in d.fields:
                if not isinstance(f.ctype, CType):
                    raise NotImplementedError("unions not implemented yet")
                type_ref: Key | CType = f.ctype
                if f.ctype.dims:
                    type_ref = resolve_array(f.ctype, d.loc)
                desc = FieldDescriptor(
                    key=Key(Table.FIELD, len(fields)),
                    loc=d.loc,
                    ntoks=sum_ntoks(f.ctype),
                    encode_len=sum_encode_len(f.ctype),
                    ctype=resolve_ctype(f.ctype, optional=not f.required),
                    name=f.name,
                    name_offset=strings.add(f.name),
                    parent=struct_key,
                    optional=not f.required,
                    type_ref=type_ref,
                )
                fields.append(desc)
        elif isinstance(d, CArray):
            spec = CType(d.elem.name, (Dim(d.min, d.max), *d.elem.dims))
            resolve_array(spec, d.loc, name=d.ctype.name)
    table = {d.key: d for d in [*structs, *fields, *arrays]}
    return strings, table


def read_and_strip(p: Path) -> str:
    return re.sub(
        r'^#include\s+"[^"]*".*\n',
        "",
        p.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )


def codegen_loaders() -> tuple[BaseLoader, ...]:
    runtime_dir = Path(__file__).resolve().parent / "runtime"
    runtime_mapping = {
        "jsmn.h": read_and_strip(runtime_dir / "jsmn.h"),
        "runtime.h": read_and_strip(runtime_dir / "runtime.h"),
        "runtime.c": read_and_strip(runtime_dir / "runtime.c"),
    }
    runtime_loader = DictLoader(runtime_mapping)
    package_loader = PackageLoader("jsmn_tools", "jsmn/templates")
    return runtime_loader, package_loader


class CodegenBundle(TypedDict):
    original: list[CDecl]
    declarations: list[CDecl]
    table: dict[Key, Descriptors]
    descriptors: list[Descriptors]
    strings: list[tuple[int, str]]
    specifications: list[dict]


def bundle_codegen(reg: Registry) -> tuple[Resolver, CodegenBundle]:
    resolver = reg.resolver()
    flattened = flatten_registry(reg)
    specifications = [
        r.contents
        for r in reg.values()
        if "openapi" in r.contents or "asyncapi" in r.contents
    ]
    sorted_user = sort_declarations(flattened.decls)
    extended = extend_declarations(sorted_user)
    strings, table = build_tables(sorted_user)
    descriptors = sorted(table.values(), key=lambda d: d.key.pos)
    return resolver, CodegenBundle(
        original=sorted_user,
        declarations=extended,
        descriptors=descriptors,
        table=table,
        strings=list(strings.strings()),
        specifications=specifications,
    )


def extract_loader(loader: BaseLoader | None) -> list[BaseLoader]:
    if isinstance(loader, ChoiceLoader):
        return list(loader.loaders)
    elif loader is not None:
        return [loader]
    else:
        return []


def join_loaders(*loaders: BaseLoader | None) -> ChoiceLoader:
    extracted = [extract_loader(loader) for loader in loaders]
    return ChoiceLoader([nested for loader in extracted for nested in loader])


def _deep_merge_globals(dst: dict, src: dict) -> None:
    """Recursively merge src into dst.

    - dict + dict -> recurse
    - list + list -> extend in place
    - anything else -> replace
    Lets workspace plugins each contribute keys (dicts) or items (lists)
    to a shared global without clobbering. Dedup is the caller's problem
    since list elements may not be hashable.
    """
    for key, value in src.items():
        existing = dst.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            _deep_merge_globals(existing, value)
        elif isinstance(value, list) and isinstance(existing, list):
            existing.extend(value)
        else:
            dst[key] = value


def join_jinja(*envs: Environment) -> Environment:
    # TODO: env settings (trim_blocks, lstrip_blocks, etc.) are hardcoded.
    #       Accept **kwargs to allow callers to override, or inherit from
    #       the first env.
    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    for other in envs:
        jinja_env.filters.update(other.filters)
        jinja_env.tests.update(other.tests)
        jinja_env.loader = join_loaders(jinja_env.loader, other.loader)
        _deep_merge_globals(jinja_env.globals, other.globals)
    return jinja_env


def extend_codegen(
    dst: Environment,
    src: CodegenBundle,
    *,
    resolver: Resolver,
    prefix: str | None = None,
    shim_mode: ShimMode | None = ShimMode.EXTERN,
) -> None:
    runtime_loader, package_loader = codegen_loaders()
    dst.loader = join_loaders(dst.loader, runtime_loader, package_loader)
    dst.tests.update(tests(src["original"], resolver))
    dst.filters.update(filters(src["table"], src["declarations"], resolver))
    dst.globals.update(src)
    dst.globals.setdefault("prefix", prefix or "jsmn_")
    dst.globals.setdefault("default_shim_mode", shim_mode or ShimMode.EXTERN)


# NOTE currently the bundle pipeline for doc tooling is join(). However, should
#      more preprocessing happen for the doc step, we would add prepare.docs ->
#      DocBundle in the future
# def docs(*specs, draft) -> DocBundle: ...
