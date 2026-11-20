from pathlib import Path
from typing import Any

import pytest
from jsmn_tools.node import Behavior
from jsmn_tools.spec import OPENAPI_3_1
from jsmn_tools.walk import normalize
from ruamel.yaml import YAML

yaml = YAML(typ="safe")


@pytest.fixture
def walk_data() -> dict[str, Any]:
    walk = Path(__file__).parent.parent.absolute() / "fixtures" / "join"
    return {file.stem: yaml.load(file) for file in walk.glob("*.yaml")}


def test_normalize_refs(walk_data: dict[str, Any]) -> None:
    """$ref values are rewritten in schema-aware contexts but left
    untouched inside data traps (default, x-*)."""
    result = normalize(walk_data["refs"], (OPENAPI_3_1, Behavior()))
    schemas = result["components"]["schemas"]

    # Direct $ref — local, unchanged
    assert schemas["direct"]["$ref"] == "#/components/schemas/target"

    # Properties: local unchanged, scheme ref collapsed to fragment
    props = schemas["in_properties"]["properties"]
    assert props["local"]["$ref"] == "#/components/schemas/target"
    assert props["external"]["$ref"] == "#/components/schemas/Foo"

    # allOf: scheme and relative refs both collapsed to fragment
    allOf = schemas["in_properties"]["allOf"]
    refs = sorted(item["$ref"] for item in allOf)
    assert refs == ["#/components/schemas/Bar", "#/components/schemas/Baz"]

    # $ref with sibling keys — ref rewritten, siblings preserved
    assert schemas["with_siblings"]["$ref"] == "#/components/schemas/target"
    assert schemas["with_siblings"]["description"] == "has sibling keys"

    # definitions (the pre-2019-09 $defs) is a map of schemas: its keys are
    # names, so one that looks like an extension is still a schema
    legacy = schemas["in_definitions"]["definitions"]["x-legacy"]
    assert legacy["$ref"] == "#/components/schemas/Qux"

    # A property NAMED "$ref" is a name: its schema is normalized like any
    named = schemas["named_ref"]["properties"]["$ref"]
    assert named == {"$ref": "#/components/schemas/Quux"}

    # Data traps — $ref is just data, NOT rewritten
    traps = schemas["data_traps"]
    assert traps["default"]["$ref"] == "#/not_a_real_ref"
    assert traps["x-meta"]["$ref"] == "forge://sdk/common/v0#/not_a_real_ref"


def test_normalize_nested_list_keeps_order(walk_data: dict[str, Any]) -> None:
    """An identity sorts the list it is declared on, not a list inside it:
    an array-valued enum member is a value, and its order is part of it."""
    result = normalize(walk_data["nested_lists"], (OPENAPI_3_1, Behavior()))
    schema = result["components"]["schemas"]["matrix"]
    assert schema["enum"] == ["b", [3, 1, 2]]
    assert schema["examples"] == [[7, 6], [9, 8]]
