import shutil
from pathlib import Path

import pytest
from jinja2 import Environment
from referencing import Registry

from jsmn_tools.plugin.loader import Loader, render

FIXTURE = Path(__file__).parent.parent.absolute() / "fixtures" / "zephyr"
RENDER = FIXTURE / "render"


def _workspace(root: Path) -> list[Path]:
    return [d for d in root.iterdir() if d.is_dir()]


def _collect(workspace: list[Path], config: dict = {}) -> Registry:
    loader = Loader(config)
    plugins = loader.load_plugins(workspace)
    resources = [r for p in plugins.values() for r in p.collect(loader)]
    return resources @ Registry()


def test_collect() -> None:
    """Test that collect discovers all project specs and creates registry."""
    registry = _collect(_workspace(FIXTURE))

    expected_keys = {
        "zephyr://sdk/common/v0",
        "zephyr://sdk/auth/v0",
        "zephyr://sensors/temperature/v0",
        "zephyr://sensors/humidity/v0",
        "zephyr://network/ethernet/v0",
        "zephyr://network/wifi/v0",
    }

    actual_keys = set(registry.keys())
    assert actual_keys == expected_keys

    resolver = registry.resolver()
    for k in registry:
        assert resolver.lookup(k).contents["$id"] == k


def test_collect_with_config() -> None:
    """Test that loader.config reaches .jsmn-tools.py collect()."""
    config = {"build_dir": "/tmp/build"}
    registry = _collect(_workspace(FIXTURE), config=config)

    assert len(registry) == 6


def test_collect_skips_dirs_without_config(tmp_path: Path) -> None:
    """Test that directories without .jsmn-tools.py are silently skipped."""
    (tmp_path / "no_config").mkdir()
    plugins = Loader().load_plugins([tmp_path / "no_config"])

    assert len(plugins) == 0


def test_collect_invalid_plugin(tmp_path: Path) -> None:
    """Test that a malformed plugin raises during collect."""
    project = tmp_path / "bad"
    project.mkdir()
    config = project / ".jsmn-tools.py"
    config.write_text("def collect(loader):\n    return 'not a list'\n")

    with pytest.raises(Exception):
        _collect([project])


def test_render_with_custom_env(tmp_path: Path) -> None:
    """Test that render uses a caller-provided jinja env with custom filters."""
    ws = tmp_path / "ws"
    shutil.copytree(RENDER / "accumulate", ws)
    plugins = Loader().load_plugins(_workspace(ws))
    registry = _collect(_workspace(ws))

    jinja_env = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    for plugin in plugins.values():
        extend = getattr(plugin, "extend", None)
        if extend:
            extend(jinja_env)

    tpl = ws / "mod_b" / "tpl.jinja2"
    out = ws / "mod_b" / "out.txt"
    errors = render((tpl, out), registry=registry, jinja_env=jinja_env)
    assert not errors
    assert out.read_text() == "HELLO"


def test_render_without_custom_env(tmp_path: Path) -> None:
    """Test that render creates its own jinja env when none is provided."""
    ws = tmp_path / "ws"
    shutil.copytree(RENDER / "accumulate", ws)
    registry = _collect(_workspace(ws))

    tpl = tmp_path / "simple.jinja2"
    out = tmp_path / "simple.txt"
    tpl.write_text("hello")

    errors = render((tpl, out), registry=registry)
    assert not errors
    assert out.read_text() == "hello"
