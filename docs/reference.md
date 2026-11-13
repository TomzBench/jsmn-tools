## Reference

<!--
NOTE (draft — rewrite for end users later):

CLI-loaded specs get `$id = path.resolve().as_uri()` (→ `file://...`). This is
intentional and composes with the `referencing` library:

- `Loader.load_resource` (plugin/loader.py) stamps a `file://` $id only when
  the spec doesn't declare one.
- `file://` is in `_PASSTHROUGH_SCHEMES` (node/uri.py) — the normalizer leaves
  it alone.
- `normalize` only runs on the bundle/join path (walk/join.py:50). It does
  NOT run during render.
- During render, `referencing` resolves `$ref`s using each doc's $id as the
  base URI. Relative refs like `./common.yaml#/...` compose against the
  file:// base → another file:// URI → registry lookup succeeds.
- Authors never write absolute paths. They write relative refs exactly like
  ordinary OpenAPI / JSON Schema.

User-facing mental model to capture on this page:

    List every spec you want to reference on the command line. Use relative
    $refs (`./sibling.yaml#/...`) — the CLI handles the rest.

Gotcha to document: both specs must be passed in the same invocation. No
retrieval callback is wired on the resolver, so an unloaded sibling dies at
flatten time as a broken ref.
-->

### CLI

Jsmn Tools installs a single `jsmn` executable exposing four subcommands.
`jsmn --help` lists them; `jsmn <sub> --help` prints per-subcommand usage.

#### jsmn cmake-dir

Prints the path to Jsmn Tools' CMake module directory. Consumer projects
use it to locate `JsmnToolsConfig.cmake` ahead of `find_package`.

```console
$ jsmn cmake-dir
/usr/local/lib/python3.X/site-packages/jsmn_tools/cmake/modules
```

See `examples/cmake/CMakeLists.txt` for typical usage.

#### jsmn bundle

Joins one or more OpenAPI / AsyncAPI specs into a single spec per draft
on disk. Useful for downstream tooling that expects a single file (e.g.,
Redocly, Stoplight, openapi-generator).

```console
$ jsmn bundle [SPECS...] --out-dir DIR [--plugin PATH] [--env K=V]...
              [--conflicts warn|error] [--conflict-lines N]
```

| Argument | Description |
|----------|-------------|
| `SPECS` | Zero or more YAML spec files. |
| `--out-dir` | **Required.** Directory that receives `openapi.yaml` / `asyncapi.yaml`. |
| `--plugin PATH` | Plugin module or directory; its `collect(loader)` hook contributes additional specs. |
| `--env K=V` | Config entry passed to the plugin. Repeatable. |
| `--conflicts warn\|error` | `warn` (default) reports conflicts and writes the output. `error` reports them, writes nothing and exits 1. |
| `--conflict-lines N` | Cap the difference lines printed per conflict. Default: every line. |

The inputs share one namespace. Containers are merged: each spec may add
paths, methods and path parameters to a path, and entries to
`components`. Named definitions are not: a schema (or any other
`components` entry), a field of an operation, and an AsyncAPI channel,
operation or server defined differently by two specs is a conflict, and
the first spec's definition is kept whole. The same definition appearing
in two specs is not a conflict.

Each conflict gives both definitions as `<spec $id>#<pointer>`, the one
kept first, and lists what differs. A spec without a `$id` is named by its
`file://` path.

```
warning: conflict: zephyr://app/poe/v0#/components/schemas/port vs zephyr://app/switch/v0#/components/schemas/port
  /required/0: "enabled" != "speed"
  /properties/enabled: only in zephyr://app/poe/v0
  /properties/speed: only in zephyr://app/switch/v0
```

Lists are compared position by position, so a difference inside a set
such as `required` reads as the positions that differ, not as the members
added or removed.

`info` and root-level `x-*` extensions describe one input, not the joined
API: the first spec's are used and a disagreement is not reported. `$id`
names one input too, and is left out of the output.

A `$ref` into another input (`./sibling.yaml#/x`, `scheme://module/name/vN#/x`)
is rewritten to the local `#/x`. A local ref with no target in the joined
document is reported as a warning.

#### jsmn render

Renders user-supplied Jinja templates against the loaded specs. The
primary escape hatch — full control over output layout and contents. All
custom-rendering examples (`examples/amalgamate`, `examples/shared_runtime`,
`examples/plugin`) drive this command.

```console
$ jsmn render [SPECS...]
              --template TPL OUT [--template TPL OUT]...
              [--plugin PATH]
              [--prefix PREFIX]
              [--shim-mode {extern,inline,none}]
              [--env K=V]... [--global K=V]...
              [--depfile FILE]
```

| Argument | Description |
|----------|-------------|
| `SPECS` | Zero or more YAML spec files. Merged with any plugin-provided specs. |
| `--template TPL OUT` | Template file and its output path. Repeatable. |
| `--plugin PATH` | Plugin module or directory. See [Plugin](#plugin). |
| `--prefix PREFIX` | Function / type-name prefix applied across all `x-jsmn-type` schemas. Default `jsmn_`. Overridden by per-schema `x-jsmn-prefix`. |
| `--shim-mode` | Default typed-shim emission: `extern` (bodies in `.c`), `inline` (`static inline` in `.h`), or `none` (no shims — callers invoke `jt_encode` / `jt_decode` directly with a `JSMN_<T>_KEY`). Default `extern`. Overridden by per-schema `x-jsmn-shim`. |
| `--env K=V` | Config entry passed to the plugin as `loader.config`. Repeatable. |
| `--global K=V` | Jinja template global. Repeatable. |
| `--depfile FILE` | Write a Make-style depfile (`outputs: inputs`) listing every file the run read: specs, plugin modules, templates and anything the plugin read through its loader. For `add_custom_command(DEPFILE)`. |

#### jsmn generate

Thin wrapper around `render` that emits the standard trio — `jsmn.h`,
`<NAME>.h`, `<NAME>.c` — into an output directory. For projects that
don't need custom rendering.

```console
$ jsmn generate [SPECS...]
                --name NAME --out-dir DIR
                [--plugin PATH]
                [--prefix PREFIX]
                [--shim-mode {extern,inline,none}]
                [--env K=V]... [--global K=V]...
                [--depfile FILE]
```

| Argument | Description |
|----------|-------------|
| `--name` | **Required.** Base name for the emitted `<NAME>.h` / `<NAME>.c`. |
| `--out-dir` | **Required.** Directory that receives generated files. |
| *others* | Same semantics as `jsmn render`. |
