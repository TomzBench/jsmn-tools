import sys
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from jsmn_tools import cli

yaml = YAML(typ="safe")

FIXTURES = Path(__file__).parent.parent.absolute() / "fixtures" / "bundle"


def _bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *flags: str
) -> Path:
    out = tmp_path / "out"
    specs = [str(FIXTURES / "a.yaml"), str(FIXTURES / "b.yaml")]
    argv = ["jsmn", "bundle", *specs, "--out-dir", str(out), *flags]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    return out / "openapi.yaml"


def test_bundle_warns_and_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    doc = yaml.load(_bundle(tmp_path, monkeypatch))
    err = capsys.readouterr().err.splitlines()
    assert err == [
        "warning: conflict: scheme://m/a/v0#/components/schemas/port "
        "vs scheme://m/b/v0#/components/schemas/port",
        "  /properties/enabled: only in scheme://m/a/v0",
        "  /properties/speed: only in scheme://m/b/v0",
        "warning: dangling $ref: openapi.yaml#/components/schemas/gone: "
        "#/components/schemas/missing",
    ]
    # $id, info and root extensions: the first spec's, and no conflict
    assert "$id" not in doc
    assert doc["info"]["title"] == "a"
    assert doc["x-vendor"] == "a"
    # a ref into another input points into the joined document
    schemas = doc["components"]["schemas"]
    assert schemas["user"]["$ref"] == "#/components/schemas/name"
    assert list(schemas["port"]["properties"]) == ["enabled"]


def test_bundle_conflicts_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit:
        _bundle(tmp_path, monkeypatch, "--conflicts", "error")
    assert exit.value.code == 1
    err = capsys.readouterr().err.splitlines()
    assert err[0].startswith("error: conflict: scheme://m/a/v0#/components/")
    assert err[-1] == "error: conflicts joining specs; nothing written"
    assert not (tmp_path / "out" / "openapi.yaml").exists()


def test_bundle_conflict_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _bundle(tmp_path, monkeypatch, "--conflict-lines", "1")
    err = capsys.readouterr().err.splitlines()
    assert err[1:3] == [
        "  /properties/enabled: only in scheme://m/a/v0",
        "  ... 1 more",
    ]


def test_bundle_joins_cli_specs_and_plugin_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clash between a command-line spec and a plugin spec is reported,
    and names both; a spec without $id is named by its file."""
    out = tmp_path / "out"
    argv = ["jsmn", "bundle", str(FIXTURES / "unnamed.yaml")]
    argv += ["--plugin", str(FIXTURES), "--out-dir", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    err = capsys.readouterr().err.splitlines()
    a = (FIXTURES / "unnamed.yaml").resolve().as_uri()
    assert err[0] == (
        f"warning: conflict: {a}#/components/schemas/port "
        "vs scheme://m/b/v0#/components/schemas/port"
    )
    doc = yaml.load(out / "openapi.yaml")
    assert "$id" not in doc
    assert set(doc["components"]["schemas"]) == {"port", "user", "name", "gone"}
