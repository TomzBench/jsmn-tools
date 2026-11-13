from pathlib import Path
from typing import Any

import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from ruamel.yaml import YAML

from jsmn_tools.jsmn.filters import (
    camel_case,
    filters,
    snake_case,
)
from jsmn_tools.jsmn.filters import (
    tests as jinja_tests,
)
from jsmn_tools.jsmn.prepare import bundle_codegen

yaml = YAML(typ="safe")
FIXTURES = Path(__file__).parent.parent / "fixtures" / "render"


@pytest.fixture()
def tag_tests() -> dict[str, Any]:
    spec = FIXTURES / "jsmn-tags.openapi.yaml"
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry: Registry[Any] = [resource] @ Registry()
    resolver, compiled = bundle_codegen(registry)
    return jinja_tests(compiled["original"], resolver)


def _find_decl(tag_tests, compiled_original, name):
    """Find a decl by name from the original declarations."""
    for d in compiled_original:
        if d.ctype.name == name:
            return d
    raise ValueError(f"decl {name} not found")


@pytest.fixture()
def originals() -> list:
    spec = FIXTURES / "jsmn-tags.openapi.yaml"
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry: Registry[Any] = [resource] @ Registry()
    _, bundle = bundle_codegen(registry)
    return bundle["original"]


def test_tagged_string(tag_tests, originals) -> None:
    """x-jsmn-tag: 'network' matches 'network', not 'other'."""
    decl = _find_decl(tag_tests, originals, "tagged_string")
    assert tag_tests["tagged"](decl, "network") is True
    assert tag_tests["tagged"](decl, "other") is False


def test_tagged_list(tag_tests, originals) -> None:
    """x-jsmn-tag: ['network', 'config'] matches both."""
    decl = _find_decl(tag_tests, originals, "tagged_list")
    assert tag_tests["tagged"](decl, "network") is True
    assert tag_tests["tagged"](decl, "config") is True
    assert tag_tests["tagged"](decl, "other") is False


def test_tagged_empty_list(tag_tests, originals) -> None:
    """x-jsmn-tag: [] matches nothing."""
    decl = _find_decl(tag_tests, originals, "tagged_empty")
    assert tag_tests["tagged"](decl, "network") is False


def test_tagged_missing(tag_tests, originals) -> None:
    """No x-jsmn-tag on schema matches nothing."""
    decl = _find_decl(tag_tests, originals, "not_tagged")
    assert tag_tests["tagged"](decl, "network") is False


# ── snake_case ───────────────────────────────────────────────────────


def test_snake_case() -> None:
    assert snake_case("deviceStatus") == "device_status"
    assert snake_case("DeviceStatus") == "device_status"
    assert snake_case("device-status") == "device_status"
    assert snake_case("already_snake") == "already_snake"


def test_snake_case_shouty() -> None:
    assert snake_case("deviceStatus", shouty=True) == "DEVICE_STATUS"
    assert snake_case("device-status", shouty=True) == "DEVICE_STATUS"


# ── camel_case ───────────────────────────────────────────────────────


def test_camel_case() -> None:
    assert camel_case("device_status") == "deviceStatus"
    assert camel_case("device-status") == "deviceStatus"


def test_camel_case_upper() -> None:
    assert camel_case("device_status", upper=True) == "DeviceStatus"


# ── json_pointer ─────────────────────────────────────────────────────


def test_json_pointer() -> None:
    """json_pointer filter resolves $ref via resolver."""
    spec = FIXTURES / "jsmn-tags.openapi.yaml"
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry: Registry[Any] = [resource] @ Registry()
    resolver, compiled = bundle_codegen(registry)
    fns = filters(
        compiled["table"],
        compiled["declarations"],
        resolver,
    )
    result = fns["json_pointer"](
        "forge://test/tags/v0#/components/schemas/tagged_string"
    )
    assert result["type"] == "object"
    assert result["x-jsmn-type"] == "tagged_string"
    assert result["x-jsmn-tag"] == "network"


def test_json_pointer_fragment_only_with_base() -> None:
    """A fragment-only $ref resolves against the document named by base."""
    spec = FIXTURES / "jsmn-tags.openapi.yaml"
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry: Registry[Any] = [resource] @ Registry()
    resolver, compiled = bundle_codegen(registry)
    fns = filters(
        compiled["table"],
        compiled["declarations"],
        resolver,
    )
    result = fns["json_pointer"](
        "#/components/schemas/tagged_string", base="forge://test/tags/v0"
    )
    assert result["x-jsmn-type"] == "tagged_string"
