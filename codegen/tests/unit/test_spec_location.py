import pytest
from jsmn_tools.node import ROOT, Location

# --- to_pointer ---


def test_to_pointer_empty() -> None:
    assert Location().to_pointer() == ""


def test_to_pointer_simple() -> None:
    loc = Location(("components", "schemas", "widget"))
    assert loc.to_pointer() == "/components/schemas/widget"


def test_to_pointer_escape_slash() -> None:
    loc = Location(("paths", "/items", "get"))
    assert loc.to_pointer() == "/paths/~1items/get"


def test_to_pointer_escape_tilde() -> None:
    loc = Location(("a~b",))
    assert loc.to_pointer() == "/a~0b"


def test_to_pointer_escape_both() -> None:
    loc = Location(("a~/b",))
    assert loc.to_pointer() == "/a~0~1b"


# --- from_pointer ---


def test_from_pointer_empty() -> None:
    assert Location.from_pointer("") == Location()


def test_from_pointer_root() -> None:
    assert Location.from_pointer("/") == Location()


def test_from_pointer_simple() -> None:
    loc = Location.from_pointer("/components/schemas/widget")
    assert loc == ("components", "schemas", "widget")


def test_from_pointer_unescape_slash() -> None:
    loc = Location.from_pointer("/paths/~1items/get")
    assert loc == ("paths", "/items", "get")


def test_from_pointer_unescape_tilde() -> None:
    loc = Location.from_pointer("/a~0b")
    assert loc == ("a~b",)


def test_from_pointer_unescape_both() -> None:
    loc = Location.from_pointer("/a~0~1b")
    assert loc == ("a~/b",)


# --- round-trip ---


@pytest.mark.parametrize(
    "segments",
    [
        (),
        ("components", "schemas", "widget"),
        ("paths", "/items", "get"),
        ("a~b",),
        ("a~/b",),
        ("paths", "/items/{id}", "get", "responses", "200"),
    ],
)
def test_roundtrip(segments: tuple[str, ...]) -> None:
    loc = Location(segments)
    assert Location.from_pointer(loc.to_pointer()) == loc


# --- from_segments ---


def test_from_segments() -> None:
    loc = Location.from_segments("forge://test/foo", "components", "schemas")
    assert loc == ("forge://test/foo", "components", "schemas")
    assert isinstance(loc, Location)


# --- push ---


def test_push_returns_location() -> None:
    loc = Location(("a", "b"))
    child = loc.push("c")
    assert isinstance(child, Location)
    assert child == ("a", "b", "c")


def test_push_does_not_mutate() -> None:
    loc = Location(("a",))
    loc.push("b")
    assert loc == ("a",)


def test_push_from_root() -> None:
    child = ROOT.push("components")
    assert child == ("components",)
    assert isinstance(child, Location)


def test_push_chain() -> None:
    loc = Location(("a",)).push("b").push("c")
    assert loc == ("a", "b", "c")


# --- tuple compat ---


def test_indexing() -> None:
    loc = Location(("a", "b", "c"))
    assert loc[0] == "a"
    assert loc[-1] == "c"


def test_len() -> None:
    assert len(Location(("a", "b"))) == 2


def test_iteration() -> None:
    assert list(Location(("a", "b"))) == ["a", "b"]


def test_hashable() -> None:
    loc = Location(("a", "b"))
    d: dict[tuple[str, ...], str] = {loc: "value"}
    assert d[("a", "b")] == "value"


def test_unpack_extend() -> None:
    loc = Location(("a", "b"))
    extended = (*loc, "c")
    assert extended == ("a", "b", "c")


def test_equality_with_tuple() -> None:
    assert Location(("a", "b")) == ("a", "b")


DOC = {"a": {"b": [10, {"c": None}]}, "s": "text"}


def test_resolve() -> None:
    assert Location(("a", "b", "0")).resolve(DOC) == 10
    assert Location(("a", "b", 1, "c")).resolve(DOC) is None
    assert Location().resolve(DOC) is DOC


@pytest.mark.parametrize(
    "path",
    [
        ("x",),  # no such key
        ("a", "b", "5"),  # index out of range
        ("a", "b", "c"),  # list indexed by name
        ("s", "t"),  # into a scalar
        ("a", "b", "0", "c"),  # into a number
    ],
)
def test_resolve_miss_is_lookup_error(path: tuple) -> None:
    with pytest.raises(LookupError, match=Location(path).to_pointer()):
        Location(path).resolve(DOC)
    assert Location(path).get(DOC) is None
    assert Location(path).get(DOC, "fallback") == "fallback"
    assert not Location(path).exists(DOC)


def test_null_is_a_value() -> None:
    loc = Location(("a", "b", "1", "c"))
    assert loc.get(DOC, "fallback") is None
    assert loc.exists(DOC)
