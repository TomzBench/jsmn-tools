from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from jsmn_tools.node import Behavior
from jsmn_tools.spec import ASYNCAPI_3_0
from jsmn_tools.walk import join, normalize
from jsmn_tools.walk.join import JoinResult

yaml = YAML(typ="safe")


def _join(*specs: dict, draft: Any) -> JoinResult:
    """Join the way a caller must: every spec named and normalized first."""
    root = (draft, Behavior())
    named = [{"$id": f"spec:{i}", **spec} for i, spec in enumerate(specs)]
    return join(*[normalize(spec, root) for spec in named], draft=draft)


@pytest.fixture
def walk_data() -> dict[str, Any]:
    fixtures = Path(__file__).parent.parent.absolute() / "fixtures"
    walk = fixtures / "join_asyncapi"
    return {file.stem: yaml.load(file) for file in walk.iterdir()}


def test_join_channel_conflict(walk_data: dict[str, Any]) -> None:
    """A channel is a named definition: two specs defining one name
    differently conflict, and the first is kept whole."""
    a = walk_data["channel_conflict_a"]
    b = walk_data["channel_conflict_b"]
    result = _join(a, b, draft=ASYNCAPI_3_0)
    assert [c.source[1:] for c in result.conflicts] == [("channels", "status")]
    assert result.value["channels"] == a["channels"]


def test_join_channel_same_twice(walk_data: dict[str, Any]) -> None:
    a = walk_data["channel_conflict_a"]
    result = _join(a, a, draft=ASYNCAPI_3_0)
    assert result.conflicts == []


def test_join_channels_union() -> None:
    a = {"channels": {"ac": {"address": "pwr.{serial}.ac"}}}
    b = {"channels": {"batt": {"address": "pwr.{serial}.batt"}}}
    result = _join(a, b, draft=ASYNCAPI_3_0)
    assert result.conflicts == []
    assert list(result.value["channels"]) == ["ac", "batt"]


def test_join_component_message_conflict() -> None:
    a = {"components": {"messages": {"m": {"payload": {"type": "string"}}}}}
    b = {"components": {"messages": {"m": {"payload": {"type": "number"}}}}}
    result = _join(a, b, draft=ASYNCAPI_3_0)
    assert [c.source[1:] for c in result.conflicts] == [
        ("components", "messages", "m")
    ]
