from __future__ import annotations

from typing import Any

from jsmn_tools.node import (
    _NO_BHV,
    Behavior,
    MapNode,
    Node,
    SchemaKind,
    SchemaNode,
    canonical,
    data,
)

map_schema       = MapNode(SchemaKind.MAP_SCHEMA)
map_schema_enter = MapNode(SchemaKind.MAP_SCHEMA_ENTER)
map_string_set   = MapNode(SchemaKind.MAP_STRING_SET)
schema           = SchemaNode(SchemaKind.SCHEMA)
schema_enter     = SchemaNode(SchemaKind.SCHEMA_ENTER)

map_schema.configure(child=schema)
map_schema_enter.configure(child=schema_enter)
map_string_set.configure(child=data, behavior=Behavior(identity=str))

# fmt: off
_SCHEMA_KEYWORDS: dict[str, tuple[Node[Any], Behavior]] = {
    # Sub-schema maps (user-defined keys -> schemas)
    "properties":               (map_schema, _NO_BHV),
    "$defs":                    (map_schema, _NO_BHV),
    "patternProperties":        (map_schema, _NO_BHV),
    "dependentSchemas":         (map_schema, _NO_BHV),
    # Single sub-schema keywords
    "items":                    (schema, _NO_BHV),
    "additionalProperties":     (schema, _NO_BHV),
    "not":                      (schema, _NO_BHV),
    "if":                       (schema, _NO_BHV),
    "then":                     (schema, _NO_BHV),
    "else":                     (schema, _NO_BHV),
    "contains":                 (schema, _NO_BHV),
    "propertyNames":            (schema, _NO_BHV),
    "prefixItems":              (schema, _NO_BHV),
    "unevaluatedItems":         (schema, _NO_BHV),
    "unevaluatedProperties":    (schema, _NO_BHV),
    # String set map
    "dependentRequired":        (map_string_set, _NO_BHV),
    # Data-carrying keywords
    "default":                  (data, _NO_BHV),
    "example":                  (data, _NO_BHV),
    "const":                    (data, _NO_BHV),
    "examples":                 (data, Behavior(identity=canonical)),
    # OpenAPI / AsyncAPI extensions (objects, not schemas)
    "discriminator":            (data, _NO_BHV),
    "xml":                      (data, _NO_BHV),
    "externalDocs":             (data, _NO_BHV),
    # Primitive set-like arrays (sorted)
    "required":                 (data, Behavior(identity=str)),
    "enum":                     (data, Behavior(identity=canonical)),
    "type":                     (data, Behavior(identity=str)),
    # Schema set-like arrays (sorted)
    "anyOf":                    (schema, Behavior(identity=canonical)),
    "oneOf":                    (schema, Behavior(identity=canonical)),
    "allOf":                    (schema, Behavior(identity=canonical)),
}
# fmt: on

schema.configure(keywords=_SCHEMA_KEYWORDS, fallback=schema)
schema_enter.configure(keywords=_SCHEMA_KEYWORDS, fallback=schema)
