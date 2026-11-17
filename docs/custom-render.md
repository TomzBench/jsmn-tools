## Custom Rendering

By default, the system will export a source file and a header file that assumes
the header file is located adjacent to the source file. But JsmnTools ships
templates that can be patterned into your source code however way you choose.

### Shared Runtime

With custom rendering, you can choose to ship a single library, containing only
the `runtime` component, and then render the descriptor tables and shims
independent of the runtime, and resolve the symbols to the runtime at link step.

See [`examples/shared_runtime/`](https://github.com/TomzBench/jsmn-tools/tree/master/examples/shared_runtime)
for the complete, buildable project — every template, the CMakeLists, and
a `main.c` that exercises both components against the shared runtime.

### Amalgamated (single source file)

With custom rendering, you can also choose to amalgamate the entire runtime,
descriptor tables and shims into a single source file — useful when you want
one translation unit with no headers to ship and nothing to link. 

See [`examples/amalgamate/`](https://github.com/TomzBench/jsmn-tools/tree/master/examples/amalgamate)
for that variant.

### Plugin

The plugin system lets you programmatically select schemas based on
environment variables passed from the CLI, and extend the Jinja environment
directly with your own globals, filters, and tests — typical of a normal
Jinja environment.

See [`examples/plugin/`](https://github.com/TomzBench/jsmn-tools/tree/master/examples/plugin)
for the minimal shape. It renders a Markdown type catalog rather than C,
incidentally demonstrating that `jsmn render` is not C-specific — any text
output format works.
