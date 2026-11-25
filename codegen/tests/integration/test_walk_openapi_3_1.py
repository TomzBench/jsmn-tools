from pathlib import Path
from typing import Any

from jsmn_tools.spec import OPENAPI_3_1
from jsmn_tools.walk import walk
from ruamel.yaml import YAML

yaml = YAML(typ="safe")
FIXTURES = Path(__file__).parent.parent / "fixtures" / "walk"


def load(name: str) -> Any:
    return yaml.load(FIXTURES / name)


def test_walk_dicts() -> None:
    """Walk descends into nested dicts."""
    steps = list(walk(load("paths.yaml"), draft=OPENAPI_3_1))
    dicts = [s for s in steps if isinstance(s.value, dict)]
    assert len(dicts) > 1


def test_walk_lists() -> None:
    """Walk descends into list items."""
    steps = list(walk(load("paths.yaml"), draft=OPENAPI_3_1))
    lists = [s for s in steps if isinstance(s.value, list)]
    assert len(lists) > 0


def test_walk_scalars() -> None:
    """Walk yields leaf scalars."""
    steps = list(walk(load("paths.yaml"), draft=OPENAPI_3_1))
    scalars = [s for s in steps if not isinstance(s.value, (dict, list))]
    assert len(scalars) > 0


def test_walk_multi_spec() -> None:
    """Variadic walk yields steps from every spec."""
    a = load("paths.yaml")
    b = load("components.yaml")
    combined = list(walk(a, b, draft=OPENAPI_3_1))
    solo_a = list(walk(a, draft=OPENAPI_3_1))
    solo_b = list(walk(b, draft=OPENAPI_3_1))
    assert len(combined) == len(solo_a) + len(solo_b)


def test_walk_list_kinds() -> None:
    steps = walk(load("lists.yaml"), draft=OPENAPI_3_1)
    kinds = {s.location.to_pointer(): s.kind for s in steps}
    params = "/paths/~1items/parameters"
    schema = "/paths/~1items/get/responses/200/content/application~1json/schema"
    assert kinds["/servers"] == "list_server"
    assert kinds["/servers/0"] == "server"
    assert kinds["/servers/0/variables"] == "map_server_var"
    assert kinds["/security"] == "list_security"
    assert kinds["/security/0"] == "map_scope"
    assert kinds[params] == "list_parameter"
    assert kinds[f"{params}/0"] == "parameter"
    assert kinds[f"{params}/0/schema/anyOf"] == "list_schema"
    assert kinds[f"{params}/0/schema/anyOf/0"] == "schema"
    assert kinds[f"{schema}/prefixItems"] == "list_schema"
    assert kinds[f"{schema}/prefixItems/0"] == "schema"
    assert kinds[f"{schema}/enum"] == "data"
    assert kinds[f"{schema}/enum/0"] == "data"
    assert kinds[f"{schema}/enum/0/0"] == "data"
