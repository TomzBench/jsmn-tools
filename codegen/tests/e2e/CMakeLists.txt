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

# Signed tokens (x-jsmn-token). The hooks need an HMAC, so the tests build
# against a crypto library on the host. JSMN_E2E_TOKEN_CRYPTO picks it:
#   auto     OpenSSL, else Mbed TLS, else skip the token tests with a warning
#   openssl  \ required: configuring fails when the library is missing, so
#   mbedtls  / CI cannot pass by quietly skipping
set(JSMN_E2E_TOKEN_CRYPTO auto CACHE STRING "Crypto backend of the token tests")
set_property(CACHE JSMN_E2E_TOKEN_CRYPTO PROPERTY STRINGS auto openssl mbedtls)
if(NOT JSMN_E2E_TOKEN_CRYPTO MATCHES "^(auto|openssl|mbedtls)$")
  message(FATAL_ERROR "JSMN_E2E_TOKEN_CRYPTO: unknown '${JSMN_E2E_TOKEN_CRYPTO}'")
endif()

if(JSMN_E2E_TOKEN_CRYPTO MATCHES "^(auto|openssl)$")
  find_package(OpenSSL QUIET)
  if(OpenSSL_FOUND)
    set(token_crypto openssl)
    set(token_crypto_libs OpenSSL::Crypto)
  endif()
endif()
if(NOT token_crypto AND JSMN_E2E_TOKEN_CRYPTO MATCHES "^(auto|mbedtls)$")
  # Mbed TLS 3 installs a CMake package; distro packages of 2.x do not
  find_package(MbedTLS CONFIG QUIET)
  if(TARGET MbedTLS::mbedcrypto)
    set(token_crypto mbedtls)
    set(token_crypto_libs MbedTLS::mbedcrypto)
  else()
    find_library(MBEDCRYPTO_LIBRARY mbedcrypto)
    find_path(MBEDCRYPTO_INCLUDE_DIR mbedtls/md.h)
    if(MBEDCRYPTO_LIBRARY AND MBEDCRYPTO_INCLUDE_DIR)
      add_library(token_mbedcrypto UNKNOWN IMPORTED)
      set_target_properties(token_mbedcrypto PROPERTIES
        IMPORTED_LOCATION "${MBEDCRYPTO_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${MBEDCRYPTO_INCLUDE_DIR}")
      set(token_crypto mbedtls)
      set(token_crypto_libs token_mbedcrypto)
    endif()
  endif()
endif()
if(NOT token_crypto AND NOT JSMN_E2E_TOKEN_CRYPTO STREQUAL "auto")
  message(FATAL_ERROR "token tests: ${JSMN_E2E_TOKEN_CRYPTO} was requested but not found")
endif()

if(token_crypto)
  cmake_path(SET token_fixtures NORMALIZE "${workspace}/codegen/tests/fixtures/token")
  file(GLOB token_specs "${token_fixtures}/*.yaml")
  # cmake-format: off
  jsmn_render(token_source
  	TEMPLATES ${templates}/token_gen.h.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/token/token_gen.h
  			  ${templates}/token_gen.c.jinja2 ${CMAKE_CURRENT_BINARY_DIR}/token/token_gen.c
  	GLOBAL token_crypto=${token_crypto}
  	SPECS ${token_specs})
  # cmake-format: on
  add_library(token ${CMAKE_CURRENT_BINARY_DIR}/token/token_gen.h
                    ${CMAKE_CURRENT_BINARY_DIR}/token/token_gen.c)
  # jsmn.h is rendered by runtime_source
  add_dependencies(token runtime_source)
  target_include_directories(token PUBLIC "${CMAKE_CURRENT_BINARY_DIR}/token"
                                          "${CMAKE_CURRENT_BINARY_DIR}")
  target_link_libraries(token PUBLIC ${token_crypto_libs})

  add_executable(test_token test_token.c)
  target_link_libraries(test_token PRIVATE unity::framework token)
  add_test(NAME test_token COMMAND test_token)
  message(STATUS "token tests: ${token_crypto} backend")
else()
  message(WARNING "token tests skipped: neither OpenSSL nor MbedTLS found")
endif()
