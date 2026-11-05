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

Joins the `components/schemas` sections of one or more OpenAPI / AsyncAPI
specs into a single merged spec on disk. Useful for downstream tooling
that expects a single file (e.g., Redocly, Stoplight, openapi-generator).

```console
$ jsmn bundle [SPECS...] --out-dir DIR [--plugin PATH] [--env K=V]...
```

| Argument | Description |
|----------|-------------|
| `SPECS` | Zero or more YAML spec files. |
| `--out-dir` | **Required.** Directory that receives `openapi.yaml` / `asyncapi.yaml`. |
| `--plugin PATH` | Plugin module or directory; its `bundle(loader)` hook contributes additional specs. |
| `--env K=V` | Config entry passed to the plugin. Repeatable. |

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
