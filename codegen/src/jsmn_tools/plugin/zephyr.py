"""Zephyr helpers for .jsmn-tools.py plugins.

A Zephyr workspace is a west manifest of projects, each of which may carry
a plugin. A *module* plugin (a library in the workspace) only selects the
schemas it ships, with ``load_zephyr_resource``. An *application* plugin
fans out over the workspace with ``ZephyrWorkspace`` so every module's
schemas end up in one registry, with the build's Kconfig merged into
``loader.config`` for the modules to select on. The same ``Loader`` flows
through the whole chain, so the depfile of a run lists every schema, plugin
module, manifest and ``autoconf.h`` the build read.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from jinja2 import Environment
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from jsmn_tools.jsmn import join_jinja
from jsmn_tools.node import ObjectNode, SchemeURI
from jsmn_tools.plugin.loader import (
    BundleResult,
    InvalidResourceError,
    Loader,
    Plugin,
    load_bundle,
)
from jsmn_tools.spec import ASYNCAPI_3_0, OPENAPI_3_1, parse_draft, split_draft
from jsmn_tools.walk import join, prefixer

type Specs[T] = dict[ObjectNode | None, list[T]]

RE_AUTOCONF = re.compile(r"^#define\s(\S+)\s?(\S+)?$", flags=re.MULTILINE)


def _require_west():
    try:
        from west import util
        from west.manifest import Manifest
    except ImportError:
        raise ImportError(
            "Missing west. Install with: pip install jsmn-tools[zephyr]"
        )
    return util, Manifest


def parse_autoconfig(loader: Loader, build_dir: Path) -> dict[str, str]:
    """Read the build's Kconfig from autoconf.h as a {CONFIG_X: value} dict."""
    build_dir = Path(build_dir)
    if not build_dir.is_absolute():
        raise ValueError("build dir must be absolute path")
    autoconf = build_dir / "zephyr/include/generated/zephyr/autoconf.h"
    config = dict(RE_AUTOCONF.findall(loader.read_text(autoconf)))
    config["CMAKE_BINARY_DIR"] = build_dir
    return config


def parse_workspace(loader: Loader) -> list[Path]:
    """The active projects of the enclosing west workspace."""
    util, Manifest = _require_west()
    topdir = Path(util.west_topdir())
    loader.recorder.record(topdir / ".west" / "config")
    manifest = Manifest.from_topdir(topdir)
    if manifest.abspath:
        loader.recorder.record(manifest.abspath)
    dirs = [topdir / p.path for p in manifest.projects if manifest.is_active(p)]
    return list(dict.fromkeys(p.resolve() for p in dirs))


# REVIEW: per-module grouping may be dead code. The flat join
# (ZephyrWorkspace.bundle) merges all modules into 1-per-draft, and normalize
# rewrites scheme $refs to relative paths before join. The per-module
# Registry produced by join_zephyr_registry has broken cross-module ref
# resolution anyway (relative file paths don't match scheme $ids).
# Keep until atx-zdk migration confirms the flat path works end-to-end.
def split_uri(*content: Any) -> dict[SchemeURI, list[Any]]:
    schemes: dict[SchemeURI, list[Any]] = defaultdict(list)
    for c in content:
        uri = SchemeURI.parse(c["$id"])
        if uri is None:
            raise InvalidResourceError(f"Invalid scheme URI: {c['$id']}")
        schemes[uri].append(c)
    return schemes


# REVIEW: see split_uri comment — this function and load_zephyr_registry
# build a per-module Registry that is likely unnecessary. The flat join
# via ZephyrWorkspace.bundle produces a working Registry for codegen.
#
# TODO: LIMITATION: The registry is built without a retrieve callback
# or document-scoped resolvers, so fragment-only $refs (e.g.,
# "#/components/schemas/foo") cannot be resolved by the global
# resolver — it has no base_uri context. Full URIs work fine.
#
# Fix: use Registry(retrieve=...) with a zephyr:// aware callback,
# and create resolvers via registry.resolver(base_uri=...) so
# fragment-only refs resolve against the current document's $id.
#
# Call sites to validate when fixed:
#   - jsmn/flatten.py   _follow_ref()
#     (workaround: reconstructs full URI from loc[0])
#   - jsmn/filters.py   json_pointer()
#     (exposed to templates, currently only receives full URIs)
def join_zephyr_registry(specs: dict[SchemeURI, list[Any]]) -> Registry:
    res = []
    for uri, items in specs.items():
        openapi, asyncapi, other = split_draft(*items)
        joined = join(*openapi, draft=OPENAPI_3_1)
        joined_a = join(*asyncapi, draft=ASYNCAPI_3_0)
        for conflict in [*joined.conflicts, *joined_a.conflicts]:
            print(f"warning: [{conflict.id}] @ {conflict.location}")
        if joined.value:
            id = SchemeURI(uri.scheme, uri.module, "openapi", uri.version)
            joined.value["$id"] = str(id)
            res.append(joined.value)
        if joined_a.value:
            id_a = SchemeURI(uri.scheme, uri.module, "asyncapi", uri.version)
            joined_a.value["$id"] = str(id_a)
            res.append(joined_a.value)
        res.extend([o for o in other if "$id" in o])
    return res @ Registry()


def load_zephyr_resource(
    loader: Loader,
    path: Path,
    module: str,
    name: str,
    ver: int,
    prefix: str | None = None,
) -> Resource:
    """Load a module's spec under the zephyr://<module>/<name>/v<ver> $id."""
    spec = loader.read_yaml(path)
    # NOTE: $id is used by join() for conflict labels (spec identification),
    # not for registry resolution. Normalize rewrites $ref values by pattern
    # matching the scheme, independent of $id.
    uri = SchemeURI("zephyr", module, name, ver)
    spec["$id"] = str(uri)
    if prefix and (draft := parse_draft(spec)):
        spec = prefixer(spec, draft=draft, prefix=prefix)
    return Resource.from_contents(spec, DRAFT202012)


class ZephyrWorkspace:
    """The plugins of the enclosing west workspace, driven by one loader.

    Built by an application plugin from the loader it was handed. When the
    build passes ``build_dir`` (the Zephyr CMake wrappers always do), the
    build's Kconfig is merged into ``loader.config`` in place, so the module
    plugins called from here see it and can select schemas on it. Merging in
    place is idempotent: building a second ZephyrWorkspace from the same
    loader re-reads the same file into the same keys.
    """

    def __init__(self, loader: Loader) -> None:
        self.loader = loader
        if build_dir := loader.config.get("build_dir"):
            loader.config.update(parse_autoconfig(loader, Path(build_dir)))
        self.projects: list[Path] = parse_workspace(loader)
        self.plugins: dict[Path, Plugin] = loader.load_plugins(self.projects)

    def resources(self) -> list[Resource]:
        """Every module's collect(), in workspace order."""
        return [
            r
            for plugin in self.plugins.values()
            for r in plugin.collect(self.loader)
        ]

    def bundle(self) -> BundleResult:
        """One joined document per draft over the whole workspace."""
        return load_bundle(*[r.contents for r in self.resources()])

    def jinja(self) -> Environment:
        """The join of every module's jinja() environment."""
        envs: list[Environment] = [
            jinja(self.loader)
            for plugin in self.plugins.values()
            if (jinja := getattr(plugin, "jinja", None))
        ]
        return join_jinja(*envs)
