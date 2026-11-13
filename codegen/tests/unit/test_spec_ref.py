import pytest

from jsmn_tools.node import Ref
from jsmn_tools.walk.normalize import collapse_ref


@pytest.mark.parametrize(
    "raw, expected",
    [
        # local — unchanged
        ("#/components/schemas/Foo", "#/components/schemas/Foo"),
        # relative — collapse to fragment
        (
            "./auth.openapi.yaml#/components/schemas/Token",
            "#/components/schemas/Token",
        ),
        # relative, no fragment — pass through unchanged (authoring mistake)
        ("./auth.openapi.yaml", "./auth.openapi.yaml"),
        # scheme — the target is in the joined document: collapse to fragment
        (
            "forge://sdk/common/v0#/components/schemas/Bar",
            "#/components/schemas/Bar",
        ),
        ("other://mod/res/v1#/path", "#/path"),
        # scheme, no fragment — nothing to point at, unchanged
        ("forge://sdk/common/v0", "forge://sdk/common/v0"),
        # external URL — unchanged
        (
            "https://example.com/schema.json#/Foo",
            "https://example.com/schema.json#/Foo",
        ),
        # http / https / file — passthrough
        ("http://mod/res/v1#/path", "http://mod/res/v1#/path"),
        ("https://mod/res/v1#/path", "https://mod/res/v1#/path"),
        ("file://mod/res/v1#/path", "file://mod/res/v1#/path"),
    ],
)
def test_collapse_ref(raw: str, expected: str) -> None:
    assert collapse_ref(raw) == expected


def test_is_local() -> None:
    assert Ref("#/foo").is_local
    assert not Ref("./file.yaml#/foo").is_local
    assert not Ref("forge://m/r/v0#/foo").is_local


def test_is_relative() -> None:
    assert Ref("./file.yaml#/foo").is_relative
    assert not Ref("#/foo").is_relative
    assert not Ref("forge://m/r/v0#/foo").is_relative


def test_fragment() -> None:
    assert Ref("#/foo").fragment == "/foo"
    assert Ref("./file.yaml#/foo").fragment == "/foo"
    assert Ref("forge://m/r/v0#/foo").fragment == "/foo"
    assert Ref("./file.yaml").fragment is None
