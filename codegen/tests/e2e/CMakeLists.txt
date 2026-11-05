cmake_minimum_required(VERSION 3.20)
project(jsmn-tools-e2e LANGUAGES C)

# Load jsmn-tools cmake modules
find_program(python3 python REQUIRED)
execute_process(
  COMMAND python -m jsmn_tools.cli cmake-dir
  OUTPUT_VARIABLE JSMN_TOOLS_MODULES_DIR
  OUTPUT_STRIP_TRAILING_WHITESPACE)
find_package(JsmnTools REQUIRED CONFIG HINTS "${JSMN_TOOLS_MODULES_DIR}")

# NOTE we peak into runtime.c files, this is more of a unit test.
cmake_path(SET workspace NORMALIZE "${CMAKE_SOURCE_DIR}/../../../")
cmake_path(SET cmake_modules NORMALIZE "${workspace}/cmake/modules")
cmake_path(SET fixtures NORMALIZE "${workspace}/codegen/tests/fixtures/runtime")
cmake_path(SET templates NORMALIZE "${CMAKE_SOURCE_DIR}/templates")

list(APPEND CMAKE_MODULE_PATH "${cmake_modules}")
find_package(Unity REQUIRED)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
enable_testing()

# cmake-format: off
file(GLOB specs "${fixtures}/*.yaml")
message(STATUS "specs: ${fixtures} ${specs}")
jsmn_render(runtime_source
	TEMPLATES ${templates}/runtime.c.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/runtime.c
			  ${templates}/runtime.h.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/runtime.h
			  ${templates}/jsmn.h.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/jsmn.h
			  ${templates}/jsmn_generated.h.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/jsmn_generated.h
			  ${templates}/jsmn_generated.c.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/jsmn_generated.c
	SPECS ${specs})

# cmake-format: on
add_executable(test_cursor test_cursor.c)
add_dependencies(test_cursor runtime_source)
target_link_libraries(test_cursor PRIVATE unity::framework)
target_include_directories(test_cursor PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
add_test(NAME test_cursor COMMAND test_cursor)

add_executable(test_fmt test_fmt.c)
add_dependencies(test_fmt runtime_source)
target_link_libraries(test_fmt PRIVATE unity::framework)
target_include_directories(test_fmt PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
add_test(NAME test_fmt COMMAND test_fmt)

add_executable(test_tok test_tok.c)
add_dependencies(test_tok runtime_source)
target_link_libraries(test_tok PRIVATE unity::framework)
target_include_directories(test_tok PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
add_test(NAME test_tok COMMAND test_tok)

add_executable(test_tok_ex test_tok_ex.c)
add_dependencies(test_tok_ex runtime_source)
target_link_libraries(test_tok_ex PRIVATE unity::framework)
target_include_directories(test_tok_ex PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
add_test(NAME test_tok_ex COMMAND test_tok_ex)

add_executable(test_descriptor test_descriptor.c)
add_dependencies(test_descriptor runtime_source)
target_link_libraries(test_descriptor PRIVATE unity::framework)
target_include_directories(test_descriptor
                           PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
add_test(NAME test_descriptor COMMAND test_descriptor)

add_library(
  runtime
  ${CMAKE_CURRENT_BINARY_DIR}/runtime.h #
  ${CMAKE_CURRENT_BINARY_DIR}/runtime.c #
  ${CMAKE_CURRENT_BINARY_DIR}/jsmn.h #
  ${CMAKE_CURRENT_BINARY_DIR}/jsmn_generated.h #
  ${CMAKE_CURRENT_BINARY_DIR}/jsmn_generated.c #
)
target_compile_options(runtime PUBLIC -DJT_HAS_FLOAT -DJT_HAS_INT64)

add_executable(test_generated test_generated.c)
target_link_libraries(test_generated PRIVATE unity::framework runtime)
add_test(NAME test_generated COMMAND test_generated)
target_include_directories(test_generated PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")

add_executable(test_pack test_pack.c)
target_link_libraries(test_pack PRIVATE unity::framework runtime)
add_test(NAME test_pack COMMAND test_pack)
target_include_directories(test_pack PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
