"""Plugin loader and workspace utilities.

A run reads specs, plugin modules, templates and build configuration from
many places, and a build system needs to know all of them to re-run the
tool when one changes. Rather than ask every reader to remember to record
what it opened, every read funnels through one ``Loader`` that the CLI
creates per run and hands to the plugin hooks, and the loader records each
file with the run's ``Recorder`` before opening it. The loader is the only
door to the file system a plugin needs, so the recorder's ``inputs`` are
complete by construction and the CLI can hand them to CMake as a depfile.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

from jinja2 import Environment
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from ruamel.yaml import YAML

from jsmn_tools.jsmn import bundle_codegen, extend_codegen
from jsmn_tools.spec import ASYNCAPI_3_0, OPENAPI_3_1, parse_draft, split_draft
from jsmn_tools.walk import JoinConflict, join, prefixer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from os import PathLike

RE_CONFIG = re.compile(r"^\.?(jsmnTools|JsmnTools|jsmn-tools).py$")

yaml = YAML(typ="safe")


class InvalidResourceError(Exception):
    """Raised when a schema $id does not match the expected URI format."""


class InvalidPlugin(Exception):
    """Raised when workspace plugin did not return a valid Project."""


class RenderError(Exception):
    """Raised when a template fails to render."""


class BundleResult(NamedTuple):
    openapi: Any | None
    asyncapi: Any | None
    other: list[Any]
    conflicts: list[JoinConflict]


class Plugin(Protocol):
    """Plugin contract for .jsmn-tools.py modules.

    Every hook receives the run's ``Loader``. ``loader.config`` holds the
    ``--env KEY=VALUE`` entries (and, under Zephyr, the build's Kconfig).

    Required:
        collect(loader) -> list[Resource]

    Required:
        bundle(loader) -> BundleResult

    Optional:
        jinja(loader) -> Environment
    """

    collect: Callable[[Loader], list[Resource]]
    bundle: Callable[[Loader], BundleResult]


class Recorder:
    """The files a run read, for the build system.

    This is why the loader exists: CMake only re-runs a render when it knows
    what the render depended on, and the specs a plugin selects, the plugin
    modules themselves and the build's autoconf.h are invisible to it. The
    recorder is a pure spy: it never opens a file and knows nothing about
    what is in one. It collects absolute paths and writes them out as a
    Make-style depfile for ``add_custom_command(DEPFILE)``.
    """

    def __init__(self) -> None:
        self._inputs: set[Path] = set()

    def record(self, path: str | PathLike[str]) -> Path:
        """Note a file that was (or is about to be) read; return it absolute."""
        p = Path(path).absolute()
        self._inputs.add(p)
        return p

    @property
    def inputs(self) -> list[Path]:
        """Every file recorded so far, absolute, deduplicated and sorted."""
        return sorted(self._inputs)

    def write_depfile(
        self, path: str | PathLike[str], outputs: Iterable[str | PathLike[str]]
    ) -> None:
        """Write ``outputs: inputs`` in Make syntax.

        Paths are written absolute with forward slashes and spaces escaped,
        which is what Ninja and Make expect from a depfile.
        """
        outs = " ".join(_escape(Path(o).absolute()) for o in outputs)
        ins = " \\\n  ".join(_escape(p) for p in self.inputs)
        dep = Path(path)
        dep.parent.mkdir(parents=True, exist_ok=True)
        dep.write_text(f"{outs}: \\\n  {ins}\n", encoding="utf-8")


class Loader:
    """The run's reader and its parameters, handed to every plugin hook.

    Every method records the file with the run's ``Recorder`` before reading
    it, so a plugin that reads through the loader cannot leave an input out
    of the depfile. ``read_*`` returns what is in the file; ``load_*`` builds
    something from it (a $id is stamped, a module is executed).

    ``config`` rides along because the hooks receive one object: it is the
    ``--env KEY=VALUE`` dict (plus the build's Kconfig under Zephyr). Nothing
    else belongs here; a helper that neither reads nor parameterizes a run
    is somebody else's.
    """

    def __init__(
        self,
        config: dict[str, str] | None = None,
        recorder: Recorder | None = None,
    ) -> None:
        self.config: dict[str, str] = dict(config or {})
        self.recorder: Recorder = recorder or Recorder()

    def read_text(self, path: str | PathLike[str]) -> str:
        return self.recorder.record(path).read_text(encoding="utf-8")

    def read_yaml(self, path: str | PathLike[str]) -> Any:
        return yaml.load(self.recorder.record(path))

    def load_resource(
        self, path: str | PathLike[str], *, prefix: str | None = None
    ) -> Resource:
        """Load a spec as a Resource; stamp a file:// $id when it has none."""
        p = self.recorder.record(path)
        spec = yaml.load(p)
        if "$id" not in spec:
            spec["$id"] = p.resolve().as_uri()
        if prefix and (draft := parse_draft(spec)):
            spec = prefixer(spec, draft=draft, prefix=prefix)
        return Resource.from_contents(spec, default_specification=DRAFT202012)

    def load_plugin(self, path: str | PathLike[str]) -> Plugin:
        p = self.recorder.record(path)
        spec = importlib.util.spec_from_file_location("_jsmn_config", p)
        if not spec or not spec.loader:
            raise InvalidPlugin(f"Cannot load: {p}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod  # type: ignore[return-value]

    def load_plugins(self, dirs: Iterable[Path]) -> dict[Path, Plugin]:
        """Load the plugin module of every directory that has one."""
        return {
            project_dir: self.load_plugin(p)
            for project_dir in dirs
            for p in project_dir.iterdir()
            if RE_CONFIG.match(p.name)
        }


def _escape(path: Path) -> str:
    return str(path).replace("\\", "/").replace(" ", "\\ ")


def load_bundle(*specs: Any) -> BundleResult:
    openapi, asyncapi, other = split_draft(*specs)
    joined = join(*openapi, draft=OPENAPI_3_1)
    joined_a = join(*asyncapi, draft=ASYNCAPI_3_0)
    return BundleResult(
        openapi=joined.value,
        asyncapi=joined_a.value,
        other=other,
        conflicts=[*joined.conflicts, *joined_a.conflicts],
    )


def render(
    *templates: tuple[Path, Path],
    registry: Registry,
    prefix: str | None = None,
    jinja_env: Environment | None = None,
    autoconf: dict[str, str] | None = None,
    loader: Loader | None = None,
) -> list[RenderError]:
    if not jinja_env:
        jinja_env = Environment(
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    if loader is None:
        loader = Loader()

    resolver, bundle = bundle_codegen(registry)
    extend_codegen(jinja_env, bundle, resolver=resolver, prefix=prefix)

    if autoconf is not None:
        jinja_env.globals["autoconf"] = autoconf

    errors: list[RenderError] = []
    for src, dst in templates:
        try:
            tpl = loader.read_text(src)
            rendered = jinja_env.from_string(tpl).render()
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(rendered, encoding="utf-8")
        except Exception as e:
            errors.append(RenderError(f"{src}: {e}"))
    return errors
