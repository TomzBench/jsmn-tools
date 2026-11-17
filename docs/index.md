# jsmn-tools

:::{div} landing-tagline

Transform OpenAPI schemas into zero-allocation C code that can parse and
serialize JSON — powered by [jsmn](https://github.com/zserge/jsmn).

:::

## Install

::::{tab-set}

:::{tab-item} uv

```console
$ uv add jsmn-tools
```

:::

:::{tab-item} pip

```console
$ pip install jsmn-tools
```

:::

::::

Verify the install:

```console
$ jsmn --help
```

## Define a Schema

Create an OpenAPI spec with the `x-jsmn-type` extension on any schema you want
to generate code for.

```{code-block} yaml
:caption: sensor.yaml

openapi: "3.1.0"
info:
  title: Sensor API
  version: "0.1.0"
components:
  schemas:
    sensor_reading:
      type: object
      x-jsmn-type: sensor_reading
      required: [id, temperature, label]
      properties:
        id:
          type: integer
          format: uint32
        temperature:
          type: number
          format: float
        label:
          type: string
          maxLength: 16
```

The `x-jsmn-type` extension tells jsmn-tools to generate a C struct and
encode/decode functions for this schema. Without it, the schema is ignored.

## Add to Your Project

jsmn-tools provides various ways to integrate with your C project. You can use
CMake, Meson, or integrate to your build system of choice using the CLI tool
directly.

::::{tab-set}

:::{tab-item} CLI

Generate the files directly, then compile with any toolchain.

```console
$ jsmn generate sensor.yaml --out-dir src/ --name sensor
$ cc -Os -DJT_HAS_FLOAT -o main main.c src/sensor.c -Isrc/
```

Re-run `jsmn generate` whenever the spec changes. `-DJT_HAS_FLOAT` opts the
runtime into float parsing (required because `temperature` is a `float`).

:::

:::{tab-item} CMake

```{code-block} cmake
:caption: CMakeLists.txt

cmake_minimum_required(VERSION 3.20)
project(sensor C)

# Discover jsmn-tools CMake module
execute_process(
    COMMAND jsmn cmake-dir
    OUTPUT_VARIABLE JSMN_CMAKE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE)
find_package(JsmnTools REQUIRED CONFIG HINTS ${JSMN_CMAKE_DIR})

# Generate codec sources from spec (writes jsmn.h, sensor.h, sensor.c)
jsmn_generate(sensor_codegen
    SPECS  sensor.yaml
    NAME   sensor
    OUTDIR ${CMAKE_CURRENT_BINARY_DIR})

# Compile the generated .c directly into the executable. Listing it as a
# source auto-wires the codegen ordering — no add_dependencies() needed.
add_executable(main
    main.c
    ${CMAKE_CURRENT_BINARY_DIR}/sensor.c)
target_include_directories(main PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_compile_definitions(main PRIVATE JT_HAS_FLOAT)
target_compile_options(main PRIVATE -Os)
```

```console
$ cmake -B build && cmake --build build
```

:::

:::{tab-item} Meson

Use a `custom_target` to run code generation, then depend on the outputs.

```{code-block} meson
:caption: meson.build

project('sensor', 'c')

jsmn = find_program('jsmn')

sensor_gen = custom_target('sensor_codegen',
    command: [jsmn, 'generate', '@INPUT@',
             '--out-dir', '@OUTDIR@',
             '--name', 'sensor'],
    input: 'sensor.yaml',
    output: ['jsmn.h', 'sensor.h', 'sensor.c'],
)

executable('main', 'main.c', sensor_gen,
    c_args: ['-Os', '-DJT_HAS_FLOAT'])
```

```console
$ meson setup build && meson compile -C build
```

:::

::::

## Use the Generated Code

```{code-block} c
:caption: main.c

#include <stdio.h>
#include <string.h>
#include "sensor.h"

int main(void) {
    /* Encode a struct to JSON */
    struct sensor_reading reading = {
        .id = 42,
        .temperature = 23.5f,
        .label = "ambient",
    };

    uint8_t buf[256];
    int32_t n = jsmn_encode_sensor_reading(buf, sizeof(buf), &reading);
    printf("JSON: %.*s\n", n, buf);

    /* Decode JSON back to a struct */
    const char *json = "{\"id\":7,\"temperature\":18.2,\"label\":\"inlet\"}";
    struct sensor_reading decoded;
    int32_t ret = jsmn_decode_sensor_reading(
        &decoded, json, strlen(json));
    printf("id=%u temp=%.1f label=%s\n",
           decoded.id, decoded.temperature, decoded.label);

    return 0;
}
```

No heap allocation. No dependencies beyond the generated files.

```{include} how-it-works.md
```

```{include} custom-render.md
```

```{include} plugins.md
```

```{include} tokens.md
```

```{include} bundle.md
```

```{include} reference.md
```
