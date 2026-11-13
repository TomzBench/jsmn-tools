from pathlib import Path

import pytest
from ruamel.yaml import YAML

from jsmn_tools.node import Behavior
from jsmn_tools.reporter import explain, report_conflicts
from jsmn_tools.spec import OPENAPI_3_1, OPENAPI_3_1_RULES
from jsmn_tools.walk import JoinConflict, join, normalize

ROOT = (OPENAPI_3_1, Behavior())
FIXTURES = Path(__file__).parent.parent.absolute() / "fixtures"
yaml = YAML(typ="safe")


@pytest.fixture
def joined() -> tuple[dict[str, dict], dict[tuple, JoinConflict]]:
    files = (FIXTURES / "conflict" / "a.yaml", FIXTURES / "conflict" / "b.yaml")
    loaded = [yaml.load(file) for file in files]
    specs = {s["$id"]: normalize(s, ROOT) for s in loaded}
    conflicts = join(*specs.values(), draft=OPENAPI_3_1).conflicts
    return specs, {tuple(c.source[1:]): c for c in conflicts}


def test_explain_says_why(joined) -> None:
    (specs, conflicts) = joined
    port = conflicts[("components", "schemas", "port")]
    # required is a set: compared by member, not by position
    assert explain(port, specs, OPENAPI_3_1) == [
        "a#/components/schemas/port vs b#/components/schemas/port",
        "  /required/enabled: only in a",
        "  /required/speed: only in b",
        "  /properties/enabled: only in a",
        "  /properties/speed: only in b",
    ]


def test_explain_limit(joined) -> None:
    (specs, conflicts) = joined
    port = conflicts[("components", "schemas", "port")]
    assert explain(port, specs, OPENAPI_3_1, limit=1) == [
        "a#/components/schemas/port vs b#/components/schemas/port",
        "  /required/enabled: only in a",
        "  ... 3 more",
    ]
    assert explain(port, specs, OPENAPI_3_1, limit=0)[1:] == ["  ... 4 more"]


def test_explain_scalar(joined) -> None:
    (specs, conflicts) = joined
    assert explain(conflicts[("openapi",)], specs, OPENAPI_3_1) == [
        "a#/openapi vs b#/openapi",
        '  "3.1.0" != "3.0.0"',
    ]


def test_explain_identified_list(joined) -> None:
    """A clash inside a list of identified items names the item."""
    (specs, conflicts) = joined
    parameters = conflicts[("paths", "/x", "get", "parameters")]
    assert explain(parameters, specs, OPENAPI_3_1) == [
        "a#/paths/~1x/get/parameters vs b#/paths/~1x/get/parameters",
        "  /path,id: only in a",
        '  /query,limit/schema/type: "a" != "b"',
    ]


def test_report_conflicts(joined, capsys: pytest.CaptureFixture[str]) -> None:
    """Printed once each, as warnings unless the mode is error."""
    (specs, conflicts) = joined
    twice = [*conflicts.values(), *conflicts.values()]
    rules = OPENAPI_3_1_RULES
    assert not report_conflicts(twice, specs, OPENAPI_3_1, rules, limit=0)
    err = capsys.readouterr().err.splitlines()
    assert [line for line in err if not line.startswith("  ")] == [
        "warning: conflict: a#/openapi vs b#/openapi",
        "warning: conflict: a#/components/schemas/port "
        "vs b#/components/schemas/port",
        "warning: conflict: a#/paths/~1x/get/parameters "
        "vs b#/paths/~1x/get/parameters",
    ]
    assert report_conflicts(twice, specs, OPENAPI_3_1, rules, mode="error")
    assert capsys.readouterr().err.startswith("error: conflict: a#/openapi")
