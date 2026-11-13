# plugin

A minimal jsmn-tools plugin that demonstrates the two hooks the CLI
respects: `collect` and `jinja`. The plugin discovers specs
from `specs/` programmatically (no spec list on the command line) and
adds a custom Jinja filter plus a template global that the rendered
template uses.

The template itself (`catalog.md.jinja`) emits a Markdown type catalog —
showing that `jsmn render` isn't limited to C output; any text format
works.

## What's here

- `.jsmn-tools.py` — the plugin module.
- `specs/sensor.yaml` — one OpenAPI spec discovered by `collect()`.
- `catalog.md.jinja` — Markdown template that consumes the plugin's
  `banner` filter and `project_name` global, plus the standard
  `declarations` global jsmn-tools adds during render.
- `Makefile` — one-liner around `jsmn render --plugin .`.

## Prerequisites

- `jsmn` on `PATH`.
- GNU make.

## Build and run

```console
$ make run
jsmn render --plugin . --env project_name=sensor-kit --template catalog.md.jinja build/catalog.md
<!-- ======== sensor-kit ======== -->

# sensor-kit — type catalog

## `struct sensor_reading`

| field   | ctype  |
|---------|--------|
| `id`      | `uint32_t` |
| `celsius` | `float`    |
| `label`   | `char`     |
```

`make clean` removes `build/`.

## How it works

Three hook functions, each called once per render:

Each hook receives the run's `Loader`. `loader.config` is the dict
assembled from `--env KEY=VALUE` CLI flags, so the plugin can be
parameterized at invocation time, and files read through the loader
(`loader.load_resource`, `loader.read_yaml`, `loader.read_text`) are
recorded for the `--depfile` the CMake wrappers ask for.

**`collect(loader)`** is called before any spec loading. It returns a
list of `Resource` objects — same type the CLI produces from positional
`*.yaml` arguments. Here it globs `specs/*.yaml`, but nothing stops a
plugin from fetching specs over HTTP, filtering by tag, or generating
them inline.

**`jinja(loader)`** is optional. It returns a pre-populated `Environment`
that jsmn-tools then overlays with its own loaders, filters, tests,
and globals via `extend_codegen`. Filters and globals you register
here survive that overlay. This plugin registers one of each:

- `banner` (filter) — decorates a string as an HTML comment banner.
- `project_name` (global) — sourced from `loader.config`, with a
  fallback default.

## Extending further

- More filters: any callable can be added to `e.filters`.
- Custom tests: `e.tests["my_test"] = lambda x: ...`, then use
  `{% if foo is my_test %}` in templates.
- More globals: `e.globals["version"] = "0.1.0"`. Useful for stamping
  build metadata into generated artifacts.
- Loader tricks: set `e.loader` to a `ChoiceLoader` that includes
  additional template directories. jsmn-tools will join its own
  loaders onto yours, so your templates can still `{% include %}` the
  runtime payloads.
