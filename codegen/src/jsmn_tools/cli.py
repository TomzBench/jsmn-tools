"""CLI entry point for jsmn tools cli

Every command builds one Recorder and one Loader over it from --env, and
reads everything through the loader: CLI specs, the plugin module,
templates, and whatever the plugin hooks read in turn (the hooks receive
the same loader). --depfile writes the recorder's inputs as a Make-style
depfile so a build system re-runs the command when any of them changes.

jsmn bundle [specs...] [--plugin PATH] [--env K=V...] --out-dir DIR
            [--conflicts warn|error] [--conflict-lines N]
    - CLI specs: loader.load_resource(path) auto-assigns file:// $id
    - Plugin: plugin.collect(loader)
    - Both: one list, split by draft, each draft normalized and joined once
    - Write to out-dir: openapi.yaml, asyncapi.yaml

jsmn render [specs...] [--plugin PATH] [--env K=V...] [--global K=V...]
            [--template SRC OUT...] [--prefix PREFIX] [--depfile FILE]
    - CLI specs: loader.load_resource(path) auto-assigns file:// $id -> Registry
    - Plugin: plugin.collect(loader) -> Registry
    - Both: CLI resources @ plugin registry (combined)
    - Plugin jinja: plugin.jinja(loader) -> Environment (optional)
    - bundle_codegen(registry) -> flatten + codegen pipeline -> render templates
"""

import argparse
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any, NoReturn

from jinja2 import Environment
from referencing import Registry, Resource
from ruamel.yaml import YAML

from jsmn_tools.jsmn.flatten import flatten_registry
from jsmn_tools.jsmn.prepare import (
    ShimMode,
    bundle_codegen,
    extend_codegen,
    sort_declarations,
)
from jsmn_tools.lang import python, typescript
from jsmn_tools.node import Behavior
from jsmn_tools.plugin.loader import Loader, Plugin, Recorder
from jsmn_tools.reporter import report_conflicts, report_dangling
from jsmn_tools.spec import (
    ASYNCAPI_3_0,
    ASYNCAPI_3_0_RULES,
    OPENAPI_3_1,
    OPENAPI_3_1_RULES,
    ConflictRules,
    split_draft,
)
from jsmn_tools.walk import join, normalize

JSMN_RUNTIME_DIR = files("jsmn_tools").joinpath("jsmn", "runtime")
RUNTIME_FILES = ("runtime.c", "runtime.h", "jsmn.h")


def _die(fmt: str, *args: object) -> NoReturn:
    print(f"error: {fmt % args}" if args else f"error: {fmt}", file=sys.stderr)
    sys.exit(1)


def _cmake_dir() -> str:
    pkg = files("jsmn_tools").joinpath("cmake")
    if Path(str(pkg)).is_dir():
        return str(pkg)
    # Editable install: cmake/ lives at repo root, not inside the package.
    repo = Path(__file__).resolve().parents[3]
    fallback = repo / "cmake" / "modules"
    if fallback.is_dir():
        return str(fallback)
    raise FileNotFoundError("Cannot locate jsmn tools cmake modules")


def _resolve_plugin(path: str, loader: Loader) -> Plugin:
    p = Path(path)
    if p.is_file():
        return loader.load_plugin(p)
    if p.is_dir():
        plugins = loader.load_plugins([p])
        if not plugins:
            _die("no .jsmn-tools.py found in %s", path)
        return next(iter(plugins.values()))
    _die("plugin path does not exist: %s", path)


def _parse_kv(items: list[str]) -> dict[str, str]:
    return dict(e.split("=", 1) for e in items)


def _collect_resources(
    *specs: str,
    loader: Loader,
    plugin: Plugin | None = None,
    prefix: str | None = None,
) -> list[Resource]:
    """The run's specs: the files on the command line, then the plugin's."""
    resources = [loader.load_resource(Path(s), prefix=prefix) for s in specs]
    if plugin:
        resources += plugin.collect(loader)
    return resources


def _join(
    specs: list[Any],
    draft: Any,
    rules: ConflictRules,
    name: str,
    mode: str,
    lines: int | None,
) -> tuple[Any, bool]:
    """Join one draft's specs and report on it: (document, must fail)."""
    normalized = [normalize(spec, (draft, Behavior())) for spec in specs]
    result = join(*normalized, draft=draft)
    by_id = {spec["$id"]: spec for spec in normalized}
    failed = report_conflicts(
        result.conflicts, by_id, draft, rules, mode, lines
    )
    report_dangling(result.value, draft, name)
    return (result.value, failed)


def _build_jinja_environment(
    args: argparse.Namespace, loader: Loader
) -> Environment:
    prefix = getattr(args, "prefix", None)
    plugin = _resolve_plugin(args.plugin, loader) if args.plugin else None
    resources = _collect_resources(
        *args.specs,
        prefix=prefix,
        loader=loader,
        plugin=plugin,
    )
    registry = resources @ Registry()

    jinja_hook = getattr(plugin, "jinja", None) if plugin else None
    jinja_env = jinja_hook(loader) if jinja_hook else None

    env_obj = jinja_env or Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    resolver, bundle = bundle_codegen(registry)
    shim_mode = ShimMode(args.shim_mode) if args.shim_mode else None
    extend_codegen(
        env_obj,
        bundle,
        resolver=resolver,
        prefix=prefix,
        shim_mode=shim_mode,
    )

    if args.globals:
        env_obj.globals.update(_parse_kv(args.globals))

    return env_obj


# -- commands ----------------------------------------------------------------


def _cmd_cmake_dir(_args: argparse.Namespace) -> None:
    print(_cmake_dir())


def _cmd_bundle(args: argparse.Namespace) -> None:
    loader = Loader(_parse_kv(args.env))
    plugin = _resolve_plugin(args.plugin, loader) if args.plugin else None
    resources = _collect_resources(*args.specs, loader=loader, plugin=plugin)
    if not resources:
        _die("no specs provided (pass spec files or --plugin)")

    (openapi, asyncapi, other) = split_draft(*[r.contents for r in resources])
    outputs: dict[str, Any] = {}
    failed = False
    for name, draft, rules, specs in (
        ("openapi.yaml", OPENAPI_3_1, OPENAPI_3_1_RULES, openapi),
        ("asyncapi.yaml", ASYNCAPI_3_0, ASYNCAPI_3_0_RULES, asyncapi),
    ):
        if specs:
            (doc, bad) = _join(
                specs, draft, rules, name, args.conflicts, args.conflict_lines
            )
            outputs[name] = doc
            failed = failed or bad
    if failed:
        _die("conflicts joining specs; nothing written")

    # A spec of neither draft is not joined; it is written as it was read,
    # less the file:// $id the loader stamps on a spec that has none.
    for i, spec in enumerate(other):
        stamped = str(spec.get("$id", "")).startswith("file://")
        outputs[f"other.{i}.yaml"] = (
            {k: v for k, v in spec.items() if k != "$id"} if stamped else spec
        )

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    writer = YAML()
    for name, doc in outputs.items():
        writer.dump(doc, out / name)


def _cmd_render(args: argparse.Namespace) -> None:
    recorder = Recorder()
    loader = Loader(_parse_kv(args.env), recorder)
    env_obj = _build_jinja_environment(args, loader)

    for src, dst in args.templates:
        tpl = loader.read_text(src)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text(
            env_obj.from_string(tpl).render(),
            encoding="utf-8",
        )
    if args.depfile:
        recorder.write_depfile(args.depfile, [dst for _, dst in args.templates])


def _cmd_generate(args: argparse.Namespace) -> None:
    recorder = Recorder()
    loader = Loader(_parse_kv(args.env), recorder)
    env_obj = _build_jinja_environment(args, loader)
    env_obj.globals.update({"preset_header": f"{args.name}.h"})
    jsmn = env_obj.get_template("jsmn.h")
    preset_h = env_obj.get_template("preset.h")
    preset_c = env_obj.get_template("preset.c")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs = [out / "jsmn.h", out / f"{args.name}.h", out / f"{args.name}.c"]
    outputs[0].write_text(jsmn.render(), encoding="utf-8")
    outputs[1].write_text(preset_h.render(), encoding="utf-8")
    outputs[2].write_text(preset_c.render(), encoding="utf-8")
    if args.depfile:
        recorder.write_depfile(args.depfile, outputs)


_RENDERERS = {
    "python": python.render_models,
    "typescript": typescript.render_models,
}


def _cmd_types(args: argparse.Namespace) -> None:
    render = _RENDERERS.get(args.lang)
    if render is None:
        _die("unsupported --lang: %s", args.lang)
    loader = Loader(_parse_kv(args.env))
    prefix = getattr(args, "prefix", None)
    plugin = _resolve_plugin(args.plugin, loader) if args.plugin else None
    resources = _collect_resources(
        *args.specs,
        prefix=prefix,
        loader=loader,
        plugin=plugin,
    )
    registry = resources @ Registry()
    result = flatten_registry(registry)
    for err in result.errors:
        print(f"warning: {err}", file=sys.stderr)
    text = render(sort_declarations(result.decls))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


# -- argparse ----------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jsmn-tools",
        description="jsmn tools",
    )
    subparsers = parser.add_subparsers()

    # cmake-dir
    p = subparsers.add_parser("cmake-dir", help="print cmake module path")
    p.set_defaults(func=_cmd_cmake_dir)

    # bundle
    p = subparsers.add_parser("bundle", help="join and bundle specs")
    p.add_argument("specs", nargs="*", help="YAML spec files")
    p.add_argument("--plugin", metavar="PATH", help="plugin file or directory")
    p.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="config passed to plugin",
    )
    p.add_argument("--out-dir", required=True, help="output directory")
    p.add_argument(
        "--conflicts",
        choices=["warn", "error"],
        default="warn",
        help="warn: report conflicts and write; error: report and fail",
    )
    p.add_argument(
        "--conflict-lines",
        type=int,
        metavar="N",
        help="cap the difference lines printed per conflict (default: all)",
    )
    p.set_defaults(func=_cmd_bundle)

    # render
    p = subparsers.add_parser("render", help="render custom templates")
    p.add_argument("specs", nargs="*", help="YAML spec files")
    p.add_argument(
        "--template",
        nargs=2,
        action="append",
        metavar=("TEMPLATE", "OUTPUT"),
        dest="templates",
        default=[],
        help="template and output pair",
    )
    p.add_argument("--plugin", metavar="PATH", help="plugin file or directory")
    p.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="config passed to plugin",
    )
    p.add_argument(
        "--global",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        dest="globals",
        help="template variable",
    )
    p.add_argument("--prefix", help="function/type prefix (default: jsmn_)")
    p.add_argument(
        "--shim-mode",
        choices=[m.value for m in ShimMode],
        help="default typed-shim emission mode (default: extern)",
    )
    p.add_argument(
        "--depfile",
        metavar="FILE",
        help="write a Make-style depfile listing every input read",
    )
    p.set_defaults(func=_cmd_render)

    # generate (stub)
    p = subparsers.add_parser("generate", help="generate code from specs")
    p.add_argument("specs", nargs="*", help="YAML spec files")
    p.add_argument("--plugin", metavar="PATH", help="plugin file or directory")
    p.add_argument("--name", required=True, help="name of the generated files")
    p.add_argument("--out-dir", required=True, help="output directory")
    p.add_argument("--prefix", help="function/type prefix (default: jsmn_)")
    p.add_argument(
        "--shim-mode",
        choices=[m.value for m in ShimMode],
        help="default typed-shim emission mode (default: extern)",
    )
    p.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="config passed to plugin",
    )
    p.add_argument(
        "--global",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        dest="globals",
        help="template variable",
    )
    p.add_argument(
        "--depfile",
        metavar="FILE",
        help="write a Make-style depfile listing every input read",
    )
    p.set_defaults(func=_cmd_generate)

    # types
    p = subparsers.add_parser(
        "types", help="generate language model definitions from specs"
    )
    p.add_argument("specs", nargs="*", help="YAML spec files")
    p.add_argument(
        "--lang",
        required=True,
        choices=["python", "typescript"],
        help="target language for the model definitions",
    )
    p.add_argument(
        "--output", required=True, help="output file (e.g. models.pyi)"
    )
    p.add_argument("--plugin", metavar="PATH", help="plugin file or directory")
    p.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="config passed to plugin",
    )
    p.add_argument("--prefix", help="ref-resolution prefix for CLI specs")
    p.set_defaults(func=_cmd_types)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
