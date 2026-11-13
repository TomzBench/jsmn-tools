## Plugin

A Jsmn Tools Plugin is a Python module loaded via `jsmn render --plugin PATH`
(or `--plugin DIR` where `DIR` contains a `.jsmn-tools.py`). It extends the
renderer past what command-line arguments can express: programmatic spec
discovery and custom Jinja filters and globals. The CLI calls up to two
top-level hooks, each at a specific point in the render pipeline, and
passes each the run's `Loader`.

### collect(loader)

Jsmn Tools leverages the
[`referencing`](https://referencing.readthedocs.io/en/stable/) library
for intra-doc `$ref` resolution, and exposes this interface directly
to the plugin layer. Plugin authors contribute to the specification
[`Registry`](https://referencing.readthedocs.io/en/stable/api/#referencing.Registry)
via the `collect` hook by returning a list of
[`Resource`](https://referencing.readthedocs.io/en/stable/api/#referencing.Resource)
objects. Anything returned here is **merged** with specs passed on the
command line, not replaced by them.

Typical uses:

- Glob a directory of specs
- Fetch specs from a URL or artifact registry
- Generate specs inline from code

```python
from pathlib import Path

HERE = Path(__file__).parent

def collect(loader):
    return [loader.load_resource(p) for p in sorted((HERE / "specs").glob("*.yaml"))]
```

`jsmn bundle` joins the same resources: the specs on the command line,
then whatever `collect` returns. A plugin needs no hook of its own for it.
The first spec's `info` becomes the joined document's, so the order of
`collect` decides it.

### jinja(loader)

The (optional) `jinja` hook lets plugin authors extend the Jinja
`Environment` with custom filters, tests, and globals — so templates
have the full capabilities expected of a normal Jinja environment.

```python
from jinja2 import Environment

def jinja(loader):
    e = Environment(
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    e.filters["banner"] = lambda s: f"<!-- {'=' * 8} {s} {'=' * 8} -->"
    e.tests["is_public_api"] = lambda d: d.ctype.name.startswith("pub_")
    e.globals["project_name"] = loader.config.get("project_name", "untitled")
    return e
```

### The Loader and the Recorder

Every hook receives the same `jsmn_tools.plugin.Loader`, the one object a
run reads files through. It carries the plugin configuration, and before
it opens a file it records the path with the run's `Recorder`, so the CLI
can tell the build system what the run depended on. The recorder itself is
a pure spy: it never reads anything, it only collects paths and writes
them out as a depfile.

| Member | Purpose |
|--------|---------|
| `loader.config` | `dict[str, str]` assembled from `--env KEY=VALUE` flags. The escape hatch for parameterizing a plugin at invocation time — file paths, feature toggles, build metadata — without changing the plugin source. |
| `loader.read_text(path)` | Read a text file. What is in the file, nothing more. |
| `loader.read_yaml(path)` | Load a YAML document as plain data. |
| `loader.load_resource(path, *, prefix=None)` | Build a `Resource` from a spec: a `file://` `$id` is stamped when the spec has none, and `prefix` is applied. |
| `loader.recorder.record(path)` | Note a file that something else read on your behalf (a library, a subprocess) so it still counts as an input. |
| `loader.recorder.inputs` | Everything recorded so far, absolute and sorted. |

`read_*` gives you the file's contents as they are. `load_*` gives you an
object built from the file, with the side effects that implies.

```console
$ jsmn render --plugin . --env project_name=sensor-kit --env build=release ...
```

Read through the loader rather than `open()` or `yaml.load()`: a file read
any other way is invisible to the depfile, and an edit to it will not
re-run the render.

### Depfile

`jsmn render` and `jsmn generate` take `--depfile FILE` and write the
recorder's inputs as a Make-style dependency file (`outputs: inputs`), the
same thing `gcc -MD` emits. The CMake wrappers pass it to
`add_custom_command(DEPFILE)`, so after the first build a change to any
spec, plugin module, template, or other file read through the loader
re-runs only the render that read it. This needs CMake 3.20 or newer.

### Zephyr integration

Jsmn Tools provides helpers under `jsmn_tools.plugin.zephyr` for Zephyr
workspaces. They extend `loader.config` with the Kconfig symbols from the
build's `autoconf.h`, and discover schemas contributed by supporting
[west](https://docs.zephyrproject.org/latest/develop/west/index.html)
modules across the workspace. A plugin can then select schemas
programmatically based on build configuration, and reference schemas in a
multi-module project with a conventional syntax instead of hard coding paths.

A *module* plugin, the `.jsmn-tools.py` at the root of a west project,
only selects the schemas the module ships:

```python
from pathlib import Path
from jsmn_tools.plugin.zephyr import load_zephyr_resource

HERE = Path(__file__).parent

def collect(loader):
    specs = [load_zephyr_resource(loader, HERE / "schemas/common.yaml", "sdk", "common", 1)]
    if loader.config.get("CONFIG_SDK_AUTH") == "1":
        specs.append(load_zephyr_resource(loader, HERE / "schemas/auth.yaml", "sdk", "auth", 1))
    return specs
```

`load_zephyr_resource(loader, path, module, name, ver, prefix=None)` stamps
the spec with the `$id` `zephyr://<module>/<name>/v<ver>`, which is how other
schemas in the workspace `$ref` it.

An *application* plugin fans out over the workspace with
`ZephyrWorkspace`, which merges the build's Kconfig into `loader.config`
(when `build_dir` is set, as the CMake wrappers do), loads every module
plugin and calls it with the same loader:

```python
from jsmn_tools.plugin.zephyr import ZephyrWorkspace

def collect(loader):
    return ZephyrWorkspace(loader).resources()

def jinja(loader):
    return ZephyrWorkspace(loader).jinja()
```

`resources()` is every module's `collect()` and `jinja()` joins every
module's `jinja()` environment. An
application that ships its own schemas appends them to `resources()`.
