## How It Works

At the heart of jsmn-tools is the "render pipeline" which intelligently walks
your OpenAPI and AsyncAPI specifications, where no jsonschema goes unfound. Any
schema that is marked with the jsmn-tools extension `x-jsmn-type` will be
recognized as an input to the code generation renderer.

::::{tab-set}

:::{tab-item} YAML

```{code-block} yaml
:caption: user.yaml

openapi: "3.1.0"
info:
    title: Demonstration
    version: 2
components:
    schemas:
        user:
            type: object
            x-jsmn-type: user
            required:
                - name
                - password
            properties:
                name:
                    type: string
                    maxLength: 32
                password:
                    type: string
                    maxLength: 32
```

:::

:::{tab-item} Header

```{code-block} c
:caption: user.h

struct user {
    uint8_t name[32];
    uint8_t password[32];
};

int32_t jsmn_decode_user(
    struct user *dst,
    const char *src,
    uint32_t slen);

int32_t jsmn_encode_user(
    uint8_t *dst,
    uint32_t dlen,
    const struct user *src);
```

:::

::::

The `x-jsmn-type` extension is intended to be declared on any complex types such
as Objects, Arrays, and Strings. Valid candidates for code generation must be
bounded. For example, any arrays must have maxItems declared in the schema, and
any strings must have maxLength declared in the schema, so that the generated
code knows the size of the type.

:::{note}

Remember, `jsmn-tools` is intended for environments without an allocator!

:::

### Pipeline

OpenAPI and AsyncAPI schemas enter into the preprocessing layer, building
Intermediate Representation (IR) optimized for code rendering. The IR is passed
to the Jinja environment, where the `jsmn-tools` templates are rendered into
source files for your project.

```{mermaid}
flowchart LR
    A[OpenAPI / AsyncAPI] --> B[Preprocess]
    B --> C[IR]
    C --> D[Jinja]
    D --> E[C sources]
```

During the preprocessing pipeline, a `prefixing` step tells the code generator
that the `x-jsmn-type` entering the pipeline is namespaced. The generator then
follows these conventions when naming generated types and functions.

::::{grid} 1
:gutter: 2

:::{grid-item-card} No prefix

**Input**

```yaml
x-jsmn-type: sensor
```

**Output**

```c
struct sensor;
jsmn_encode_sensor(...);
jsmn_decode_sensor(...);
```

:::

:::{grid-item-card} With prefix

**Input**

```yaml
x-jsmn-type: sensor
x-jsmn-prefix: foo_
```

**Output**

```c
struct foo_sensor;
foo_encode_sensor(...);
foo_decode_sensor(...);
```

:::

:::{grid-item-card} Naively prefixed
:class-card: sd-border-danger

**Input**

```yaml
x-jsmn-type: foo_sensor
```

**Output**

<pre><code>struct foo_sensor;
<span class="jt-bad">jsmn_</span>encode_<span class="jt-bad">foo_</span>sensor(...);
<span class="jt-bad">jsmn_</span>decode_<span class="jt-bad">foo_</span>sensor(...);
</code></pre>

:::

::::

:::{note}

The `--prefix` CLI flag applies the prefix automatically to every
`x-jsmn-type` in the specifications, so you don't need to stamp
`x-jsmn-prefix` by hand on each schema.

:::

When the pipeline is finished, the rendered templates produce compile ready
source code. The (2) primary components of the rendered output files is the
**runtime** and the **descriptor tables**.

### Runtime

The runtime provides a polymorphic interface that supports **all** of the
x-jsmn-type declarations found when processing the schemas. The runtime is a
one-time ~7.5KiB cost (measured on x86 with `-Os`). A configurable "shim
layer" provides a type-safe, ergonomic API and leverages the shared runtime
algorithms for encode and decode routines.

```{mermaid}
flowchart LR
    T["`**schema**
    - openapi: 3.1.0       
    - x-jsmn-type: sensor`"] --> S["`**shim layer**
    - jsmn_encode_sensor
    - jsmn_decode_sensor`"] --> R["`**shared**
    - jsmn_encode
    - jsmn_decode`"]
```

By sharing the encode and decode algorithms across all types, the system beats
a hand-rolled alternative, where iterating tokens at the call sites would be
prohibitive on constrained embedded systems. Each additional type adds
~155 bytes, depending on the number of properties and size of the property
keys for each type.

We can see below how the system scales from 1 `x-jsmn-type` (~7.5KiB), to 100
`x-jsmn-type`s (~22.8KiB) to 500 `x-jsmn-type`s (~84.8KiB), using a sample
object with 4 properties. The chart demonstrates the contribution of the
descriptor tables and the "shim layer", which can be configured to use `static
inline` shims or `extern` declarations. The "extern" declarations are useful if
you need to export the API as a library, at the cost of losing cross-boundary
inlining.

```{image} _static/metrics_n.svg
:alt: Generated code size vs. number of x-jsmn-type schemas (calls/type = 1)
:align: center
```

The shim knobs are granular per type. You can keep the default of `static
inline` shims, and elect to export a few symbols with `extern` declarations
and provide a public-facing API for selected types.


### Descriptor Tables

Every `x-jsmn-type` contributes entries to four descriptor tables. An
**object table** and an **array table** describe each composite type —
what it contains, and where to find each member inside the C struct —
and steer the runtime through encode and decode. A **field table** lists
every declared property, and a **string table** provides an indexable
pool of property names, shared across objects: when multiple types
declare the same name, it is stored once.

A compact type handle identifies what the runtime is currently looking
at — a primitive, an entry in the object table, or an entry in the array
table. The runtime treats this handle as its only input; the tables
supply everything else.

Each descriptor row is exactly 8 bytes with no pointers, so the entire
block is read-only and ships in `.rodata`. Adding or removing schemas
grows or shrinks the tables; the runtime itself never changes.
