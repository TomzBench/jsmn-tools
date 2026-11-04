from pathlib import Path
from textwrap import dedent

import pytest
from jinja2 import Environment
from referencing import Resource
from referencing.jsonschema import DRAFT202012
from ruamel.yaml import YAML

from referencing import Registry

from jsmn_tools.jsmn.filters import ShimMode
from jsmn_tools.jsmn.prepare import bundle_codegen, extend_codegen
from jsmn_tools.jsmn.render import hoist_includes

yaml = YAML(typ="safe")
FIXTURES = Path(__file__).parent.parent / "fixtures" / "render"


@pytest.fixture(params=["jsmn", "jsmn-vla", "jsmn-every-type"])
def env(request) -> Environment:
    spec = FIXTURES / f"{request.param}.openapi.yaml"
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry = [resource] @ Registry()
    resolver, bundle = bundle_codegen(registry)
    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    extend_codegen(jinja_env, bundle, resolver=resolver, prefix="jsmn_")
    return jinja_env


@pytest.fixture()
def empty_env() -> Environment:
    resolver, bundle = bundle_codegen(Registry())
    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    extend_codegen(jinja_env, bundle, resolver=resolver, prefix="jsmn_")
    return jinja_env


def test_renderer_jsmn_generated_decl(env: Environment, snapshot) -> None:
    """Render components"""
    tpl = "{% include 'jsmn_generated.h' %}"
    assert env.from_string(tpl).render() == snapshot


def test_renderer_jsmn_generated_impl(env: Environment, snapshot) -> None:
    """Render components"""
    tpl = "{% include 'jsmn_generated.c' %}"
    assert env.from_string(tpl).render() == snapshot


def test_renderer_multi_document(snapshot) -> None:
    """Two documents in one registry render the same way run after run."""
    resources = [
        Resource.from_contents(
            yaml.load(FIXTURES / f"{name}.openapi.yaml"),
            default_specification=DRAFT202012,
        )
        for name in ("jsmn-vla", "jsmn")
    ]
    resolver, bundle = bundle_codegen(resources @ Registry())
    env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    extend_codegen(env, bundle, resolver=resolver, prefix="jsmn_")
    tpl = "{% include 'jsmn_generated.h' %}"
    assert env.from_string(tpl).render() == snapshot


def test_renderer_runtime_snapshot(empty_env: Environment, snapshot) -> None:
    """Runtime files are loadable via prefix loader with includes stripped."""
    tpl = dedent("""\
        {% include 'jsmn.h' %}
        {% include 'runtime.h' %}
        {% include 'runtime.c' %}
        """)
    assert empty_env.from_string(tpl).render() == snapshot


def test_renderer_hoist_includes(empty_env: Environment, snapshot) -> None:
    """System includes are deduplicated and hoisted to the top."""
    tpl = dedent("""\
        #include <stdint.h>
        #include <stdbool.h>
        void foo(void);
        #include <stdint.h>
        #include <string.h>
        void bar(void);
        #include <stdbool.h>
        #include <stddef.h>
        """)
    result = hoist_includes(empty_env.from_string(tpl).render())
    assert result == snapshot


# ── shim_mode coverage ──────────────────────────────────────────────
#
# One fixture (jsmn-shim-modes) carries four types — one without an
# x-jsmn-shim override, one for each of {none, extern, inline}.
# Parametrizing default_shim_mode over the same three values exercises
# every (default, override) pair across just 3 snapshots per render
# target (decl + impl = 6 snapshots total).


@pytest.fixture(params=[ShimMode.NONE, ShimMode.EXTERN, ShimMode.INLINE])
def shim_env(request) -> Environment:
    spec = FIXTURES / "jsmn-shim-modes.openapi.yaml"
    resource = Resource.from_contents(
        yaml.load(spec), default_specification=DRAFT202012
    )
    registry = [resource] @ Registry()
    resolver, bundle = bundle_codegen(registry)
    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    extend_codegen(
        jinja_env,
        bundle,
        resolver=resolver,
        prefix="jsmn_",
        shim_mode=request.param,
    )
    return jinja_env


def test_shim_modes_decl(shim_env: Environment, snapshot) -> None:
    """Decl-side shim emission under each default, per-type overrides applied."""
    tpl = "{% include 'jsmn_generated.h' %}"
    assert shim_env.from_string(tpl).render() == snapshot


def test_shim_modes_impl(shim_env: Environment, snapshot) -> None:
    """Impl-side shim emission under each default, per-type overrides applied."""
    tpl = "{% include 'jsmn_generated.c' %}"
    assert shim_env.from_string(tpl).render() == snapshot


def test_shim_mode_invalid_value_raises(empty_env: Environment) -> None:
    """x-jsmn-shim with an unknown value rejected by the filter."""
    spec = {
        "openapi": "3.1.0",
        "$id": "forge://test/shim-invalid/v0",
        "info": {"title": "Invalid shim mode", "version": "0.1.0"},
        "components": {
            "schemas": {
                "bad": {
                    "type": "object",
                    "x-jsmn-type": "bad",
                    "x-jsmn-shim": "bogus",
                    "required": ["v"],
                    "properties": {"v": {"type": "integer", "format": "uint32"}},
                }
            }
        },
    }
    resource = Resource.from_contents(spec, default_specification=DRAFT202012)
    registry = [resource] @ Registry()
    resolver, bundle = bundle_codegen(registry)
    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    extend_codegen(jinja_env, bundle, resolver=resolver, prefix="jsmn_")
    decl = bundle["original"][0]
    shim_mode_or = jinja_env.filters["shim_mode_or"]
    with pytest.raises(ValueError):
        shim_mode_or(decl, ShimMode.EXTERN)


def test_shim_mode_fallback_when_absent(empty_env: Environment) -> None:
    """No x-jsmn-shim → filter returns the caller-supplied fallback."""
    spec = {
        "openapi": "3.1.0",
        "$id": "forge://test/shim-fallback/v0",
        "info": {"title": "Fallback", "version": "0.1.0"},
        "components": {
            "schemas": {
                "plain": {
                    "type": "object",
                    "x-jsmn-type": "plain",
                    "required": ["v"],
                    "properties": {"v": {"type": "integer", "format": "uint32"}},
                }
            }
        },
    }
    resource = Resource.from_contents(spec, default_specification=DRAFT202012)
    registry = [resource] @ Registry()
    resolver, bundle = bundle_codegen(registry)
    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    extend_codegen(jinja_env, bundle, resolver=resolver, prefix="jsmn_")
    decl = bundle["original"][0]
    shim_mode_or = jinja_env.filters["shim_mode_or"]
    assert shim_mode_or(decl, ShimMode.INLINE) is ShimMode.INLINE
    assert shim_mode_or(decl, ShimMode.NONE) is ShimMode.NONE
