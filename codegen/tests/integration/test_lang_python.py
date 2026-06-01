from pathlib import Path
from typing import Any

import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from ruamel.yaml import YAML

from jsmn_tools.jsmn.flatten import flatten_registry
from jsmn_tools.jsmn.prepare import sort_declarations
from jsmn_tools.lang.python import render_models

yaml = YAML(typ="safe")
FIXTURES = Path(__file__).parent.parent / "fixtures"

# Reuse the shared C fixtures — render fixtures cover primitives, multi-dim
# arrays/VLAs, refs, optionals, and VLA strings; the runtime e2e fixtures add
# top-level aliases (top_label -> str, top_vla_points -> list[point]) and a
# broader spread of optional fields.
SPECS = [
    "render/jsmn.openapi.yaml",
    "render/jsmn-every-type.openapi.yaml",
    "render/jsmn-vla.openapi.yaml",
    "runtime/arrays.yaml",
    "runtime/optionals.yaml",
]


@pytest.fixture(params=SPECS, ids=lambda p: Path(p).stem)
def decls(request: pytest.FixtureRequest) -> list[Any]:
    spec = FIXTURES / request.param
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry = [resource] @ Registry()
    return sort_declarations(flatten_registry(registry).decls)


def test_render_models(decls: list[Any], snapshot) -> None:
    assert render_models(decls) == snapshot
