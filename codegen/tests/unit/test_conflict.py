from pathlib import Path

import pytest
from ruamel.yaml import YAML

from jsmn_tools.node import Behavior, Location
from jsmn_tools.spec import (
    ASYNCAPI_3_0_RULES,
    OPENAPI_3_1,
    OPENAPI_3_1_RULES,
    ConflictRules,
    Verdict,
)
from jsmn_tools.walk import JoinConflict, dangling, join, normalize

ROOT = (OPENAPI_3_1, Behavior())
FIXTURES = Path(__file__).parent.parent.absolute() / "fixtures"
yaml = YAML(typ="safe")


@pytest.mark.parametrize("rules", [OPENAPI_3_1_RULES, ASYNCAPI_3_0_RULES])
def test_conflict_rules(rules: ConflictRules) -> None:
    assert rules(Location(("info", "title"))) is Verdict.IGNORE
    assert rules(Location(("x-vendor",))) is Verdict.IGNORE
    assert rules(Location(("x-vendor", "deep"))) is Verdict.IGNORE
    assert rules(Location(("components", "schemas", "port"))) is Verdict.ERROR
    # an extension below the root belongs to a definition
    below = Location(("components", "schemas", "port", "x-t"))
    assert rules(below) is Verdict.ERROR


def test_conflict_rules_version() -> None:
    assert OPENAPI_3_1_RULES(Location(("openapi",))) is Verdict.ERROR
    assert ASYNCAPI_3_0_RULES(Location(("asyncapi",))) is Verdict.ERROR


@pytest.fixture
def joined() -> tuple[dict[str, dict], dict[tuple, JoinConflict]]:
    files = (FIXTURES / "conflict" / "a.yaml", FIXTURES / "conflict" / "b.yaml")
    loaded = [yaml.load(file) for file in files]
    specs = {s["$id"]: normalize(s, ROOT) for s in loaded}
    conflicts = join(*specs.values(), draft=OPENAPI_3_1).conflicts
    return specs, {tuple(c.source[1:]): c for c in conflicts}


def test_join_locates_both_sides(joined) -> None:
    (_, conflicts) = joined
    assert set(conflicts) == {
        ("openapi",),
        ("components", "schemas", "port"),
        ("paths", "/x", "get", "parameters"),
    }
    port = conflicts[("components", "schemas", "port")]
    assert port.destination == ("a", "components", "schemas", "port")
    assert port.source == ("b", "components", "schemas", "port")


def test_join_requires_ids() -> None:
    with pytest.raises(KeyError, match="id"):
        join({"$id": "a"}, {}, draft=OPENAPI_3_1)
    with pytest.raises(ValueError, match="used by two specs: a"):
        join({"$id": "a"}, {"$id": "a"}, draft=OPENAPI_3_1)
    assert join(draft=OPENAPI_3_1).value == {}


def test_join_drops_id() -> None:
    result = join({"$id": "a", "x": 1}, {"$id": "b", "y": 2}, draft=OPENAPI_3_1)
    assert result.value == {"x": 1, "y": 2}
    assert result.conflicts == []


def test_dangling() -> None:
    doc = yaml.load(FIXTURES / "dangling" / "refs.yaml")
    found = dangling(doc, OPENAPI_3_1)
    assert [(d.location.to_pointer(), d.ref) for d in found] == [
        (
            "/paths/~1x/get/responses/200/content/application~1json/schema",
            "#/components/schemas/gone",
        )
    ]
