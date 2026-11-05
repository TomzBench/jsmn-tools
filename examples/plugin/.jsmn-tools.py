"""Minimal jsmn-tools plugin.

Exposes three hooks the CLI will call, each with the run's Loader:

- collect(loader) — programmatic spec discovery. Anything returned here is
  merged with specs passed on the command line.
- bundle(loader)  — `jsmn bundle` entry point; joins the collected specs.
- jinja(loader)   — pre-populates a Jinja Environment with extra filters,
  tests, or globals before jsmn-tools overlays its own codegen bits.

`loader.config` is the dict populated from `--env KEY=VALUE` CLI flags.
Read files through the loader (`loader.load_resource`, `loader.read_yaml`,
`loader.read_text`) so they land in the run's depfile.
"""

from pathlib import Path

from jinja2 import Environment

from jsmn_tools.plugin.loader import load_bundle

HERE = Path(__file__).parent


def collect(loader):
    return [
        loader.load_resource(p) for p in sorted((HERE / "specs").glob("*.yaml"))
    ]


def bundle(loader):
    return load_bundle(*[r.contents for r in collect(loader)])


def jinja(loader):
    e = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    e.filters["banner"] = lambda s: (f"<!-- {'=' * 8} {s} {'=' * 8} -->")
    e.globals["project_name"] = loader.config.get("project_name", "untitled")
    return e
