# JsmnZephyrToolsConfig.cmake — Zephyr-aware wrappers around JsmnTools
#
# Provides jsmn_zephyr_templates(), jsmn_zephyr_application_templates(),
# and jsmn_zephyr_library_templates() with Zephyr defaults baked in.
# Does NOT auto-bundle — use find_package(JsmnZephyrApplication) for that.
#
# The specs come from the plugins: the application's .jsmn-tools.py fans out
# over the west workspace (ZephyrWorkspace) and every module's collect()
# selects its schemas on the build's Kconfig. CMake never sees that list;
# the depfile the render writes does, so a schema, plugin or Kconfig change
# re-runs the render on the next build. Callers may still pass SPECS for
# files outside the plugin chain.
#
# Example (library):
#
#   jsmn_zephyr_library_templates(
#       TEMPLATES   ${CMAKE_SOURCE_DIR}/api.h.j2  ${CMAKE_BINARY_DIR}/api.h
#                   ${CMAKE_SOURCE_DIR}/api.c.j2  ${CMAKE_BINARY_DIR}/api.c
#   )
#
# Example (custom target):
#
#   jsmn_zephyr_templates(my_codegen_target
#       TEMPLATES   ${CMAKE_SOURCE_DIR}/foo.h.j2  ${CMAKE_BINARY_DIR}/foo.h
#   )

execute_process(
  COMMAND jsmn cmake-dir
  OUTPUT_VARIABLE JSMN_TOOLS_MODULES_DIR
  OUTPUT_STRIP_TRAILING_WHITESPACE)
find_package(JsmnTools REQUIRED HINTS ${JSMN_TOOLS_MODULES_DIR})

# Render templates for a named target with Zephyr defaults.
# First positional arg is the target name; remaining args forwarded to jsmn_render.
# Caller's single-value args (PLUGIN, PREFIX) override defaults, while
# multi-value args (ENV, SPECS) accumulate.
function(jsmn_zephyr_templates target)
    jsmn_render(${target}
        PLUGIN  ${CMAKE_SOURCE_DIR}
        ENV     build_dir=${CMAKE_BINARY_DIR}
        ${ARGN}
    )
endfunction()

# Render templates for the Zephyr application.
# Creates an app_codegen target and wires it as a dependency of app.
function(jsmn_zephyr_application_templates)
    jsmn_zephyr_templates(app_codegen ${ARGN})
    add_dependencies(app app_codegen)
endfunction()

# Render templates for a Zephyr library.
# Creates a ${ZEPHYR_CURRENT_LIBRARY}_codegen target and wires it as a
# dependency of ZEPHYR_CURRENT_LIBRARY so generated files exist before
# the library compiles.
function(jsmn_zephyr_library_templates)
    jsmn_zephyr_templates(${ZEPHYR_CURRENT_LIBRARY}_codegen ${ARGN})
    add_dependencies(${ZEPHYR_CURRENT_LIBRARY} ${ZEPHYR_CURRENT_LIBRARY}_codegen)
endfunction()
