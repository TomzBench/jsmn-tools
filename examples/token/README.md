# token

Sign a session token at login and verify it on later requests, with the
claims declared as a schema. See [Signed tokens](../../docs/tokens.md).

## What's here

- `session.yaml` — a `session` schema marked `x-jsmn-token`, which is what
  asks for the sign/verify pair.
- `main.c.jinja` — a Jinja template that `{% include %}`s the jsmn source,
  the runtime, the token runtime, the generated codec and a crypto backend,
  followed by a `main()` that signs a token and verifies four variations
  of it.
- `Makefile` — runs `jsmn render` to produce `build/main.c`, then compiles
  and links it against the crypto library.

## Prerequisites

- `jsmn` on `PATH`.
- GNU make and a C compiler.
- OpenSSL development files (`libssl-dev`), or pick another backend below.

## Build and run

```console
$ make run
jsmn render session.yaml --global token_crypto=openssl --template main.c.jinja build/main.c
cc -Os -Wall -o build/main build/main.c -lcrypto
./build/main
token:    eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJpbnN0YWxsZXIiLCJyb2xlIjoyLCJleHAiOjEwMDB9.Gujp7plClFV86o5ahKkJO9yh31HswTqvEBUPXTkm-uU
valid     accepted: sub=installer role=2 exp=1000
late      rejected: expired
tampered  rejected: bad signature
other key rejected: bad signature
```

The token is an ordinary HS256 JWT: paste it into any JWT decoder to read
the header and the claims.

## How it works

`x-jsmn-token: { alg: HS256 }` on the schema makes
`jsmn_token_generated.{h,c}` emit `jsmn_token_sign_session`,
`jsmn_token_verify_session` and `JSMN_SESSION_TOKEN_LEN`, the longest token
the schema can produce. `main()` sizes its buffer with that macro, so nothing
is allocated and nothing is guessed.

`exp` is a required claim, so the generated verify takes the current time
and rejects the token once it is reached. The example passes plain numbers;
a device passes its clock, or its uptime if it has no clock.

The runtime does no hashing. It calls `jt_mac_sign` and `jt_mac_verify`,
which `jsmn_token_crypto.c` defines for the backend named by
`--global token_crypto=...`. To use another one:

```console
$ make clean
$ make run CRYPTO=mbedtls
```

`CRYPTO=psa` renders the PSA Crypto backend, where `jt_key.data` points at a
key handle instead of key bytes. `main()` here passes key bytes, so it needs
changing to import a key first before that backend will work.
