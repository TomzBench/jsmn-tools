# Jsmn Tools

## Intro

jsmn-tools is a code generation project. jsmn-tools generates code by
crawling OpenAPI specifications and AsyncAPI specifications for "JSON Schemas".
Code generation must be explicitly declared via OpenAPI and AsyncAPI extension.

More details are in the design document. You should only need to consult the
design document when you are assigned a task.

## Design Pushback

If you identify a design flaw in what I'm asking for, stop and flag it before
implementing. Explain the concern and propose an alternative. Don't implement
something you know is wrong just because I asked for it.

Specific things to watch for:
- Adding indirection (wrappers, abstractions, registries) without a concrete
  second consumer
- Premature generalization — solving hypothetical future requirements instead of
  the actual task
- Layering workarounds on top of a bad foundation instead of fixing the
  foundation
- Duplicating logic that should be factored, or factoring logic that only has
  one call site

When in doubt, push back with a short explanation and an alternative. I'd rather
have a 30-second conversation than undo a bad design later.

## Git Commits

Always use `git commit -s` for the Signed-off-by line. Never write
Signed-off-by manually — it has led to fabricated names in the past.

## Code Structure

```
codegen/
  src/jsmn_tools/
    cli.py          # CLI entry point
    bundle.py       # Bundle logic for code generation
    node/           # Node types, behaviors, locations, refs
    spec/           # Spec structure definitions (OpenAPI 3.1, JSON Schema)
    walk/           # Tree operations (walk, normalize, diff, merge, join)
    lang/jsmn/      # C code generation (IR types, flatten, templates, runtime)
  tests/
    fixtures/       # Test fixtures (specs, templates)
    unit/           # Unit tests
    integration/    # Integration tests
    e2e/            # Full end to end C integration test (via CMake)
```
