from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import reduce
from typing import TYPE_CHECKING, Any
from urllib.parse import urldefrag

from jsmn_tools.jsmn.ir import CArray, CDecl, CStruct, CType, Dim, Field
from jsmn_tools.node import Location, ObjectNode
from jsmn_tools.spec import ASYNCAPI_3_0, OPENAPI_3_1
from jsmn_tools.walk import Step, walk

if TYPE_CHECKING:
    from referencing import Registry
    from referencing._core import Resolver


@dataclass
class ConstraintViolation:
    location: Location


@dataclass
class BrokenRef:
    ref: str


@dataclass
class UnsupportedSchemaFormat:
    location: Location
    schema_format: str


type FlattenError = ConstraintViolation | BrokenRef | UnsupportedSchemaFormat


@dataclass
class FlattenResult:
    decls: dict[CType, CDecl]
    errors: list[FlattenError]

    def __ior__(self, other: FlattenResult) -> FlattenResult:
        self.decls |= other.decls
        self.errors.extend(other.errors)
        return self

    def __or__(self, other: FlattenResult) -> FlattenResult:
        return FlattenResult(
            decls={**self.decls, **other.decls},
            errors=self.errors + other.errors,
        )

    @classmethod
    def empty(cls) -> FlattenResult:
        return cls(decls={}, errors=[])


_FORMAT_MAP: dict[str, str] = {
    "uint8": "uint8_t",
    "int8": "int8_t",
    "uint16": "uint16_t",
    "int16": "int16_t",
    "uint32": "uint32_t",
    "int32": "int32_t",
    "uint64": "uint64_t",
    "int64": "int64_t",
    "float": "float",
    "double": "double",
}


class TypeKey(StrEnum):
    NULL = "null"
    BOOL = "bool"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    OBJECT = "object"
    ARRAY = "array"


def _follow_ref(
    schema: Any,
    loc: Location,
    curr_resolver: Resolver,
) -> tuple[Location, Any, Resolver]:
    ref = schema["$ref"]
    base, fragment = urldefrag(ref)
    if not base:
        base = loc[0]
        ref = f"{base}#{fragment}" if fragment else base
    location_fragment = Location.from_pointer(fragment)
    target_location = Location.from_segments(base, *location_fragment)
    resolved = curr_resolver.lookup(ref)
    return (target_location, resolved.contents, resolved.resolver)


def _seek_ctype(schema: Any, loc: Location, curr_resolver: Resolver) -> CType:  # noqa: PLR0911
    if "$ref" in schema:
        resolved = _follow_ref(schema, loc, curr_resolver)
        (target_location, target_contents, target_resolver) = resolved
        return _seek_ctype(target_contents, target_location, target_resolver)
    ty: TypeKey = schema.get("type")
    assert ty in TypeKey
    match ty:
        case TypeKey.NULL:
            return CType("null")
        case TypeKey.BOOL | TypeKey.BOOLEAN:
            return CType("bool")
        case TypeKey.INTEGER | TypeKey.NUMBER:
            fmt = schema.get("format")
            return CType(_FORMAT_MAP.get(fmt, "int32_t"))
        case TypeKey.STRING:
            max_len = schema.get("maxLength", 0)  # TODO value error
            buf = max_len + 1  # +1 for null terminator
            return CType("char", (Dim(buf, buf),))
        case TypeKey.OBJECT:
            return CType(schema.get("x-jsmn-type", ""))
        case TypeKey.ARRAY:
            min_items = schema.get("minItems", 0)
            max_items = schema.get("maxItems", 0)  # TODO value error
            items = schema.get("items")
            if items is None:
                raise ValueError(f"array without items: {schema}")
            dim = Dim(min_items, max_items)
            inner = _seek_ctype(items, loc, curr_resolver)
            return CType(inner.name, (dim, *inner.dims))


@dataclass
class Properties:
    _required: set[str]
    _properties: list[tuple[str, Any]]

    def __ior__(self, other: Properties) -> Properties:
        self._required |= other._required
        self._properties.extend(other._properties)
        return self

    @classmethod
    def empty(cls) -> Properties:
        return cls(set(), [])

    @classmethod
    def from_object(
        cls,
        schema: Any,
        loc: Location,
        resolver: Resolver,
    ) -> Properties:
        # TODO this is last branch wins when allOf branches declare duplicate names
        # TODO silently ignores allOf branch is a primitive
        props = cls.empty()
        for branch in schema.get("allOf", []):
            if "$ref" in branch:
                (rloc, rschema, rresolver) = _follow_ref(branch, loc, resolver)
                props |= cls.from_object(
                    rschema,
                    rloc,
                    rresolver,
                )
            elif branch.get("type") == "object" or "allOf" in branch:
                props |= cls.from_object(branch, loc, resolver)

        for p in schema.get("properties", {}).items():
            props._properties.append(p)
        props._required |= set(schema.get("required", []))
        return props

    def properties(self) -> Iterator[tuple[bool, str, Any]]:
        for name, schema in self._properties:
            yield name in self._required, name, schema


# Walk complex types (objects, arrays, $refs, and (eventually) compositional
def _walk_any(
    schema: Any,
    loc: Location,
    curr_resolver: Resolver,
) -> FlattenResult:
    ty: TypeKey = schema.get("type", "object")
    if ty == "object" and "x-jsmn-type" in schema:
        fresult = FlattenResult.empty()
        fields: list[Field] = []
        properties_location = loc.push("properties")
        props = Properties.from_object(schema, loc, curr_resolver)
        for required, prop_name, prop_schema in props.properties():
            # NOTE: object properties have their own locations
            prop_loc = properties_location.push(prop_name)
            prop_ctype = _seek_ctype(prop_schema, prop_loc, curr_resolver)
            fields.append(Field(prop_name, prop_ctype, required))
            fresult |= _walk_any(prop_schema, prop_loc, curr_resolver)
        ctype = CType(schema["x-jsmn-type"])
        fresult.decls |= {ctype: CStruct(ctype, loc, fields)}
        return fresult
    elif ty == "array":
        prop_loc = loc.push("items")
        items = schema.get("items")
        if "x-jsmn-type" in schema:
            ctype = CType(schema["x-jsmn-type"])
            carr = CArray(
                ctype=ctype,
                elem=_seek_ctype(items, prop_loc, curr_resolver),
                loc=loc,  # NOTE Array locations are the array node
                min=schema.get("minItems", 0),
                max=schema.get("maxItems", 0),  # TODO value error
            )
            fresult = _walk_any(items, prop_loc, curr_resolver)
            fresult.decls |= {ctype: carr}
            return fresult
        else:
            return _walk_any(items, prop_loc, curr_resolver)

    elif ty == "string" and "x-jsmn-type" in schema:
        ctype = CType(schema["x-jsmn-type"])
        max_len = schema.get("maxLength", 0)  # TODO value error
        buf = max_len + 1  # +1 for null terminator
        carr = CArray(
            ctype=ctype,
            elem=CType("char"),
            loc=loc,  # NOTE: Array locations capture the array node
            min=buf,
            max=buf,
        )
        return FlattenResult(decls={ctype: carr}, errors=[])

    elif "$ref" in schema:
        resolved = _follow_ref(schema, loc, curr_resolver)
        (target_location, contents, target_resolver) = resolved
        return _walk_any(contents, target_location, target_resolver)
    elif "allOf" in schema:
        fresult = FlattenResult.empty()
        for branch in schema["allOf"]:
            fresult |= _walk_any(branch, loc, curr_resolver)
        return fresult
    elif any(k in schema for k in ("anyOf", "oneOf")):
        raise NotImplementedError
    else:
        return FlattenResult.empty()


# Walk spec and get locations of all structs
def flatten_with_resolver[K: str](
    *specs: Any,
    resolver: Resolver,
    draft: ObjectNode[K] = OPENAPI_3_1,
) -> FlattenResult:
    def step(acc: FlattenResult, s: Step[K]) -> FlattenResult:
        if s.kind == "schema_enter" and isinstance(s.value, dict):
            if "schemaFormat" in s.value:
                e = UnsupportedSchemaFormat(s.location, s.value["schemaFormat"])
                acc.errors.append(e)
            elif "x-jsmn-type" in s.value:
                ty = s.value.get("type")
                if ty in ("object", "array", "string") or "allOf" in s.value:
                    acc |= _walk_any(s.value, s.location, resolver)
        return acc

    return reduce(step, walk(*specs, draft=draft), FlattenResult.empty())


def flatten_registry(reg: Registry) -> FlattenResult:
    """Flatten every OpenAPI/AsyncAPI document in a registry into one IR result.

    Splits documents by draft (presence of an ``openapi``/``asyncapi`` key) and
    runs each under the matching grammar. This is the language-neutral entry
    point shared by the C codegen bundle and the model backends in
    jsmn_tools.lang.
    """
    openapi = [r.contents for r in reg.values() if "openapi" in r.contents]
    asyncapi = [r.contents for r in reg.values() if "asyncapi" in r.contents]
    resolver = reg.resolver()
    result = flatten_with_resolver(
        *openapi, resolver=resolver, draft=OPENAPI_3_1
    )
    result |= flatten_with_resolver(
        *asyncapi, resolver=resolver, draft=ASYNCAPI_3_0
    )
    return result
