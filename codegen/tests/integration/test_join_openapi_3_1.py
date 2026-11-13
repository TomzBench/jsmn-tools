from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from jsmn_tools.node import Behavior
from jsmn_tools.spec import OPENAPI_3_1
from jsmn_tools.walk import diff, join, normalize
from jsmn_tools.walk.join import JoinResult

yaml = YAML(typ="safe")


def _join(*specs: dict, draft: Any) -> JoinResult:
    """Join the way a caller must: every spec named and normalized first."""
    root = (draft, Behavior())
    named = [{"$id": f"spec:{i}", **spec} for i, spec in enumerate(specs)]
    return join(*[normalize(spec, root) for spec in named], draft=draft)


@pytest.fixture
def walk_data() -> dict[str, Any]:
    walk = Path(__file__).parent.parent.absolute() / "fixtures" / "join"
    return {file.stem: yaml.load(file) for file in walk.iterdir()}


def test_join_schema_sets(walk_data: dict[str, Any]) -> None:
    """Schema-level set arrays (required, enum, type, oneOf) normalize
    to the same result regardless of authoring order."""
    test_files = (walk_data["schema_sets_a"], walk_data["schema_sets_b"])
    result = _join(*test_files, draft=OPENAPI_3_1)
    assert result.conflicts == []
    widget = result.value["components"]["schemas"]["widget"]
    assert widget["required"] == ["alpha", "beta"]
    assert widget["properties"]["alpha"]["type"] == ["null", "string"]
    assert widget["properties"]["alpha"]["enum"] == ["fast", "slow"]
    # oneOf sorted by canonical:
    # {"format":..,"type":"integer"} < {"maxLength":..,"type":"string"}
    assert widget["properties"]["beta"]["oneOf"][0]["type"] == "integer"
    assert widget["properties"]["beta"]["oneOf"][1]["type"] == "string"


def test_join_openapi_sets(walk_data: dict[str, Any]) -> None:
    """OpenAPI-level set arrays (parameters, tags, security, scopes,
    server_var.enum) normalize equivalently regardless of order."""
    test_files = (walk_data["openapi_sets_a"], walk_data["openapi_sets_b"])
    result = _join(*test_files, draft=OPENAPI_3_1)
    assert result.conflicts == []
    op = result.value["paths"]["/items"]["get"]
    assert op["tags"] == ["admin", "inventory"]
    # parameters sorted by (in, name): path/id < query/limit
    assert op["parameters"][0]["name"] == "id"
    assert op["parameters"][0]["in"] == "path"
    assert op["parameters"][1]["name"] == "limit"
    assert op["parameters"][1]["in"] == "query"
    # security sorted by canonical: apiKey < oauth
    assert list(op["security"][0].keys()) == ["apiKey"]
    assert list(op["security"][1].keys()) == ["oauth"]
    # security scopes sorted by str
    assert op["security"][1]["oauth"] == ["read", "write"]
    # server_var.enum sorted by str
    server_var = result.value["servers"][0]["variables"]["env"]
    assert server_var["enum"] == ["prod", "staging"]


def test_join_ordered(walk_data: dict[str, Any]) -> None:
    """Ordered arrays (servers, prefixItems, root tags) must NOT be
    sorted by normalize — different authoring order stays different."""
    a = walk_data["ordered_a"]
    b = walk_data["ordered_b"]
    result = _join(a, b, draft=OPENAPI_3_1)
    # Ordered arrays produce positional conflicts/differences
    assert result.conflicts != []
    # Verify the diffs are real — normalize preserves order
    merged_a = _join(a, draft=OPENAPI_3_1)
    merged_b = _join(b, draft=OPENAPI_3_1)
    assert diff(merged_a.value, merged_b.value) != {}


def test_join_union(walk_data: dict[str, Any]) -> None:
    """A schema is a named definition: one defined differently by two specs
    is a conflict and is not merged; a new schema is deep-copied."""
    test_files = (walk_data["merge_union_a"], walk_data["merge_union_b"])
    result = _join(*test_files, draft=OPENAPI_3_1)
    schemas = result.value["components"]["schemas"]
    # alpha: one conflict at the definition, the first spec's kept whole
    (conflict,) = result.conflicts
    assert conflict.destination == ("spec:0", "components", "schemas", "alpha")
    assert conflict.source == ("spec:1", "components", "schemas", "alpha")
    assert schemas["alpha"]["required"] == ["name"]
    assert list(schemas["alpha"]["properties"]) == ["name"]
    # beta: deep-copied from b
    assert "beta" in schemas
    assert schemas["beta"]["properties"]["active"]["type"] == "boolean"


def test_join_same_definition_twice() -> None:
    """The same definition in two specs is not a conflict."""
    spec = {"components": {"schemas": {"a": {"type": "string"}}}}
    result = _join(spec, {**spec}, draft=OPENAPI_3_1)
    assert result.conflicts == []
    assert result.value == spec


def test_join_path_fragments(walk_data: dict[str, Any]) -> None:
    """Specs may each add methods and parameters to one path."""
    test_files = (walk_data["path_fragments_a"], walk_data["path_fragments_b"])
    result = _join(*test_files, draft=OPENAPI_3_1)
    assert result.conflicts == []
    item = result.value["paths"]["/x"]
    assert set(item) == {"get", "put", "parameters"}
    assert [p["name"] for p in item["parameters"]] == ["id", "n"]


def test_join_path_method_conflict(walk_data: dict[str, Any]) -> None:
    """The same method defined differently by two specs is a conflict at
    the field that differs; the first spec's is kept."""
    test_files = (walk_data["path_fragments_a"], walk_data["path_fragments_c"])
    result = _join(*test_files, draft=OPENAPI_3_1)
    assert [x.source[1:] for x in result.conflicts] == [
        ("paths", "/x", "get", "responses")
    ]
    assert result.value["paths"]["/x"]["get"]["responses"] == {"200": {}}


def test_join_security_schemes() -> None:
    a = {"components": {"securitySchemes": {"k": {"scheme": "basic"}}}}
    b = {"components": {"securitySchemes": {"k": {"scheme": "bearer"}}}}
    result = _join(a, b, draft=OPENAPI_3_1)
    assert [x.source[1:] for x in result.conflicts] == [
        ("components", "securitySchemes", "k")
    ]


def test_join_conflict(walk_data: dict[str, Any]) -> None:
    """Conflicting scalars and parameter identity produce MergeConflict
    objects with correct locations."""
    test_files = (walk_data["merge_conflict_a"], walk_data["merge_conflict_b"])
    result = _join(*test_files, draft=OPENAPI_3_1)
    locs = {c.source[1:] for c in result.conflicts}
    assert ("info", "title") in locs
    assert ("info", "version") in locs
    # parameter with same (in, name) but different schema
    assert ("paths", "/items", "get", "parameters") in locs
    assert len(result.conflicts) == 3


def test_join_schema_dispatch(walk_data: dict[str, Any]) -> None:
    """Data traps (default, x-*) preserve content unchanged while
    schema-aware paths (dependentRequired, $defs, enum, examples) sort."""
    test_files = (
        walk_data["schema_dispatch_a"],
        walk_data["schema_dispatch_b"],
    )
    result = _join(*test_files, draft=OPENAPI_3_1)
    assert result.conflicts == []
    gadget = result.value["components"]["schemas"]["gadget"]
    name_prop = gadget["properties"]["name"]
    # default is a data trap — unsorted array preserved
    assert name_prop["default"]["required"] == ["zebra", "apple"]
    # x-meta is a data trap — unsorted array preserved
    assert name_prop["x-meta"]["tags"] == ["beta", "alpha"]
    # dependentRequired values sorted as string sets
    assert gadget["dependentRequired"]["name"] == ["desc", "label"]
    # $defs recurse into schema — enum and examples sorted
    mode = gadget["$defs"]["mode"]
    assert mode["enum"] == ["off", "on"]
    assert mode["examples"] == ["off", "on"]
