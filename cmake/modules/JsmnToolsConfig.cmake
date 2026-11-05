# JsmnToolsConfig.cmake — thin wrappers around the jsmn CLI
#
# Example:
#
#   find_package(JsmnTools REQUIRED)
#
#   jsmn_bundle(
#       SPECS   specs/openapi.yaml
#       PLUGIN  ${CMAKE_CURRENT_SOURCE_DIR}
#       OUTDIR  ${CMAKE_CURRENT_BINARY_DIR}/cache
#       ENV     build_dir=${CMAKE_CURRENT_BINARY_DIR}
#   )
#
#   jsmn_render(my_codegen_target
#       SPECS       ${CMAKE_CURRENT_BINARY_DIR}/cache/openapi.yaml
#       PLUGIN      ${CMAKE_CURRENT_SOURCE_DIR}
#       TEMPLATES   ${CMAKE_CURRENT_SOURCE_DIR}/api.h.j2  ${CMAKE_CURRENT_BINARY_DIR}/api.h
#                   ${CMAKE_CURRENT_SOURCE_DIR}/api.c.j2  ${CMAKE_CURRENT_BINARY_DIR}/api.c
#       PREFIX      my_app_
#       ENV         build_dir=${CMAKE_CURRENT_BINARY_DIR}
#       GLOBAL      version=1.0
#   )
#
#   jsmn_generate(my_codegen_target
#       SPECS       ${CMAKE_CURRENT_BINARY_DIR}/cache/openapi.yaml
#       PLUGIN      ${CMAKE_CURRENT_SOURCE_DIR}
#       PREFIX      app_
#       ENV         build_dir=${CMAKE_CURRENT_BINARY_DIR}
#       GLOBAL      version=1.0
#       NAME        app
#       OUTDIR      ${CMAKE_CURRENT_BINARY_DIR}/generated
#   )
#
# Produces three files in OUTDIR: jsmn.h, <NAME>.h, <NAME>.c. Consumers add
# the generated .c to their own target and declare a dependency on the
# codegen target — jsmn_generate does not wrap the output in a library.
#
# Both jsmn_render and jsmn_generate ask the tool for a depfile (--depfile)
# and hand it to add_custom_command(DEPFILE). The tool lists every file the
# run read: the SPECS, the plugin module and every spec it collected, the
# templates, and under Zephyr the west manifest and the build's autoconf.h.
# So an edit to any of them re-runs the render on the next build without a
# pristine configure. DEPFILE with Ninja and Makefile generators needs
# CMake 3.20 (policy CMP0116), which is also Zephyr's minimum.

set(JsmnTools_FOUND TRUE)
set(JsmnTools_VERSION "0.1.0")
find_program(JsmnTools_EXECUTABLE jsmn REQUIRED)

# Append ARGN to ${var} only when ${cond} is truthy.
# Uses a macro (not a function) so list(APPEND) mutates the caller's scope.
# Avoids generator expressions which pass "" on Windows when condition is false.
macro(_append_if cond var)
    if(${cond})
        list(APPEND ${var} ${ARGN})
    endif()
endmacro()

function(jsmn_render target)
    cmake_parse_arguments(ARG "" "PREFIX;PLUGIN" "SPECS;TEMPLATES;ENV;GLOBAL" ${ARGN})

    # Validate TEMPLATES (required, must be SRC OUT pairs)
    list(LENGTH ARG_TEMPLATES _tpl_len)
    if(_tpl_len EQUAL 0)
        message(FATAL_ERROR "jsmn_render: TEMPLATES is required")
    endif()
    math(EXPR _tpl_rem "${_tpl_len} % 2")
    if(_tpl_rem)
        message(FATAL_ERROR "jsmn_render: TEMPLATES must be SRC OUT pairs (got ${_tpl_len} items)")
    endif()

    # Build command args
    set(_args ${ARG_SPECS})

    # Build --template pairs and collect outputs
    math(EXPR _tpl_end "${_tpl_len} - 1")
    foreach(i RANGE 0 ${_tpl_end} 2)
        math(EXPR j "${i} + 1")
        list(GET ARG_TEMPLATES ${i} tpl)
        list(GET ARG_TEMPLATES ${j} out)
        list(APPEND _args --template "${tpl}" "${out}")
        list(APPEND _depends "${tpl}")
        list(APPEND _outputs "${out}")
    endforeach()

    # Build --env args (user-defined environment variables)
    foreach(e IN LISTS ARG_ENV)
        list(APPEND _args --env "${e}")
    endforeach()

    # Build --global args (user defined template variables)
    foreach(g IN LISTS ARG_GLOBAL)
        list(APPEND _args --global "${g}")
    endforeach()

    # Build optional arguments
    _append_if(ARG_PREFIX _args --prefix "${ARG_PREFIX}")
    _append_if(ARG_PLUGIN _args --plugin "${ARG_PLUGIN}")

    set(_depfile "${CMAKE_CURRENT_BINARY_DIR}/${target}.d")
    list(APPEND _args --depfile "${_depfile}")

    add_custom_command(
        OUTPUT ${_outputs}
        COMMAND ${JsmnTools_EXECUTABLE} render ${_args}
        DEPENDS ${ARG_SPECS} ${_depends}
        DEPFILE ${_depfile}
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        COMMENT "jsmn-tools: generating outputs"
    )

    add_custom_target(${target} DEPENDS ${_outputs})
endfunction()

function(jsmn_generate target)
    cmake_parse_arguments(ARG "" "PREFIX;PLUGIN;NAME;OUTDIR" "SPECS;ENV;GLOBAL" ${ARGN})

    # Validate required arguments
    if(NOT ARG_NAME)
        message(FATAL_ERROR "jsmn_generate: NAME is required")
    endif()
    if(NOT ARG_OUTDIR)
        message(FATAL_ERROR "jsmn_generate: OUTDIR is required")
    endif()

    # Build command args
    set(_args ${ARG_SPECS})

    # Build --env args (user-defined environment variables)
    foreach(e IN LISTS ARG_ENV)
        list(APPEND _args --env "${e}")
    endforeach()

    # Build --global args (user defined template variables)
    foreach(g IN LISTS ARG_GLOBAL)
        list(APPEND _args --global "${g}")
    endforeach()

    # Build optional arguments
    _append_if(ARG_PREFIX _args --prefix "${ARG_PREFIX}")
    _append_if(ARG_PLUGIN _args --plugin "${ARG_PLUGIN}")

    list(APPEND _args --name "${ARG_NAME}" --out-dir "${ARG_OUTDIR}")

    set(_depfile "${CMAKE_CURRENT_BINARY_DIR}/${target}.d")
    list(APPEND _args --depfile "${_depfile}")

    set(_outputs
        "${ARG_OUTDIR}/jsmn.h"
        "${ARG_OUTDIR}/${ARG_NAME}.h"
        "${ARG_OUTDIR}/${ARG_NAME}.c"
    )

    add_custom_command(
        OUTPUT ${_outputs}
        COMMAND ${JsmnTools_EXECUTABLE} generate ${_args}
        DEPENDS ${ARG_SPECS}
        DEPFILE ${_depfile}
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        COMMENT "jsmn-tools: generating ${ARG_NAME}"
    )

    add_custom_target(${target} DEPENDS ${_outputs})
endfunction()

function(jsmn_bundle)
    cmake_parse_arguments(ARG "" "PLUGIN;OUTDIR" "SPECS;ENV" ${ARGN})

    # Build command args
    set(_args ${ARG_SPECS})

    # Build --env args (user-defined environment variables)
    foreach(e IN LISTS ARG_ENV)
        list(APPEND _args --env "${e}")
    endforeach()

    # Validate OUTDIR (required)
    if(ARG_OUTDIR)
        list(APPEND _args --out-dir ${ARG_OUTDIR})
    else()
        message(FATAL_ERROR "jsmn_bundle: OUTDIR is required")
    endif()

    # Build optional arguments
    _append_if(ARG_PLUGIN _args --plugin "${ARG_PLUGIN}")

    execute_process(
        COMMAND ${JsmnTools_EXECUTABLE} bundle ${_args}
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        RESULT_VARIABLE _rc
        ERROR_VARIABLE _err
    )
    if(_rc)
        message(FATAL_ERROR "jsmn_bundle: ${_err}")
    endif()
endfunction()
