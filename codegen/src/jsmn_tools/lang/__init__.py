"""Non-C language backends.

Each backend consumes the language-neutral IR (the output of flatten +
sort_declarations) and emits type definitions for a target language. These
sit above jsmn_tools.jsmn in the layering and depend only on the IR
(jsmn_tools.jsmn.ir) and primitives — never on the C lowering pipeline
(prepare / mangle / descriptor / runtime).
"""
