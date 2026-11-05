"""The Recorder collects what a run read; the Loader reads through it."""

import sys
from pathlib import Path

import pytest

from jsmn_tools import cli
from jsmn_tools.plugin.loader import Loader, Recorder
from jsmn_tools.plugin.zephyr import load_zephyr_resource, parse_autoconfig

FIXTURE = Path(__file__).parent.parent.absolute() / "fixtures" / "zephyr"
SPEC = (
    "openapi: '3.1.0'\n"
    "info: {title: t, version: '1'}\n"
    "components: {schemas: {}}\n"
)


def test_recorder_inputs_absolute_sorted_deduplicated(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    recorder = Recorder()
    assert recorder.record("b.txt") == tmp_path / "b.txt"
    recorder.record(tmp_path / "a.txt")
    recorder.record(Path("b.txt"))
    assert recorder.inputs == [tmp_path / "a.txt", tmp_path / "b.txt"]
    assert all(p.is_absolute() for p in recorder.inputs)


def test_recorder_depfile_format(tmp_path: Path) -> None:
    recorder = Recorder()
    recorder.record(tmp_path / "with space.yaml")
    dep = tmp_path / "out" / "t.d"
    recorder.write_depfile(dep, [tmp_path / "x.h", "y.c"])
    outs, ins = dep.read_text().split(":", 1)
    assert outs == f"{tmp_path / 'x.h'} {Path('y.c').absolute()}"
    assert ins == f" \\\n  {tmp_path}/with\\ space.yaml\n"


def test_loader_defaults() -> None:
    env = {"k": "v"}
    loader = Loader(env)
    loader.config["other"] = "x"
    assert env == {"k": "v"}, "config is copied"
    assert Loader().config == {}
    assert isinstance(Loader().recorder, Recorder)
    recorder = Recorder()
    assert Loader(recorder=recorder).recorder is recorder


def test_loader_reads_record(tmp_path: Path) -> None:
    spec = tmp_path / "spec.yaml"
    spec.write_text(SPEC)
    side = tmp_path / "side.txt"
    side.write_text("side")
    plugin = tmp_path / ".jsmn-tools.py"
    plugin.write_text(
        "from pathlib import Path\n"
        "HERE = Path(__file__).parent\n"
        "def collect(loader):\n"
        "    loader.read_text(HERE / 'side.txt')\n"
        "    return [loader.load_resource(HERE / 'spec.yaml')]\n"
    )
    loader = Loader()
    mod = loader.load_plugins([tmp_path])[tmp_path]
    resources = mod.collect(loader)
    assert resources[0].contents["$id"] == spec.resolve().as_uri()
    assert loader.read_yaml(spec)["openapi"] == "3.1.0"
    assert loader.recorder.inputs == [plugin, side, spec]


def test_zephyr_helpers_record(tmp_path: Path) -> None:
    loader = Loader()
    spec = FIXTURE / "sdk" / "schemas" / "common.openapi.yaml"
    res = load_zephyr_resource(loader, spec, "sdk", "common", 0)
    assert res.contents["$id"] == "zephyr://sdk/common/v0"

    autoconf = tmp_path / "zephyr/include/generated/zephyr/autoconf.h"
    autoconf.parent.mkdir(parents=True)
    autoconf.write_text("#define CONFIG_FOO 1\n#define CONFIG_BAR y\n")
    config = parse_autoconfig(loader, tmp_path)
    assert config["CONFIG_FOO"] == "1"
    assert config["CONFIG_BAR"] == "y"
    assert config["CMAKE_BINARY_DIR"] == tmp_path
    assert loader.recorder.inputs == sorted([autoconf, spec])

    with pytest.raises(ValueError):
        parse_autoconfig(loader, Path("relative"))


def test_cli_render_depfile(tmp_path: Path, monkeypatch) -> None:
    """Every input of a render lands in the depfile: specs, plugin, side files,
    and templates."""
    spec = tmp_path / "cli.yaml"
    spec.write_text(SPEC)
    side = tmp_path / "side.txt"
    side.write_text("side")
    plugin = tmp_path / ".jsmn-tools.py"
    plugin.write_text(
        "from pathlib import Path\n"
        "HERE = Path(__file__).parent\n"
        "def collect(loader):\n"
        "    loader.read_text(HERE / 'side.txt')\n"
        "    return []\n"
        "def bundle(loader):\n"
        "    raise NotImplementedError\n"
    )
    tpl = tmp_path / "out.txt.j2"
    tpl.write_text("hello")
    out = tmp_path / "build" / "out.txt"
    dep = tmp_path / "build" / "render.d"
    argv = [
        "jsmn",
        "render",
        str(spec),
        "--plugin",
        str(tmp_path),
        "--template",
        str(tpl),
        str(out),
        "--depfile",
        str(dep),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert out.read_text() == "hello"
    text = dep.read_text()
    assert text.startswith(f"{out}: \\\n")
    inputs = [line.strip().rstrip(" \\") for line in text.splitlines()[1:]]
    assert inputs == sorted(str(p) for p in (spec, plugin, side, tpl))
