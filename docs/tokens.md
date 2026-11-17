## Signed tokens

A schema marked `x-jsmn-token` gets a typed sign/verify pair that frames its
JSON as a signed token: `base64url(header).base64url(claims).base64url(mac)`,
the JWS compact form a JWT uses. The claims are a schema like any other, so
the generated tables encode and decode them. Nothing is allocated, and every
buffer is sized from the schema.

This is a prototype. It signs with HMAC (HS256, HS384, HS512) only, which
suits a device that issues and checks its own tokens.

### Declare

```yaml
components:
  schemas:
    session:
      type: object
      x-jsmn-type: session
      x-jsmn-token: { alg: HS256 }
      required: [sub, exp]
      properties:
        sub: { type: string, maxLength: 32 }
        exp: { type: integer, format: uint32 }
```

`alg` defaults to `HS256`.

### Generated API

```c
#define JSMN_SESSION_TOKEN_LEN (...)   /* longest token, terminator excluded */

int32_t jsmn_token_sign_session(
    char *dst, uint32_t dlen,
    const struct session *claims,
    const struct jt_key *key);

int32_t jsmn_token_verify_session(
    struct session *dst,
    const char *tok, uint32_t tlen,
    const struct jt_key *key,
    uint32_t now);
```

Sign writes a NUL-terminated token and returns its length. Verify returns a
positive count on success. Both return a negative `jt_err` or `jt_token_err`
on failure, and `dst` holds claims you may use only when verify succeeded.

- **The header is compared, not parsed.** The algorithm is fixed by the
  declaration, so the encoded header is a constant in the generated code. A
  token cannot name its own algorithm.
- **The mac is checked first.** Nothing is decoded from the claims until the
  signature has matched.
- **Time claims are enforced.** When `exp` or `nbf` is a required property,
  verify takes `now` and rejects a token outside its window. `now` is
  whatever clock the claims were written against: wall time, or uptime on a
  unit that has no clock. A token with neither claim is verified without it.

### Rendering

The token code is three more includes in your templates:

| Template | Holds |
|----------|-------|
| `token.h`, `token.c` | The runtime: framing, base64url, `jt_token_sign`, `jt_token_verify`. |
| `jsmn_token_generated.h`, `jsmn_token_generated.c` | The typed pair for each `x-jsmn-token` schema. Render the `.c` in the same file as `jsmn_generated.c`, after it: it reads the schema tables that file keeps static. |
| `jsmn_token_crypto.c` | A crypto backend (optional, below). |

See [`examples/token/`](https://github.com/TomzBench/jsmn-tools/tree/master/examples/token)
for a complete, buildable project that signs a token and verifies it.

### Crypto

The runtime computes no hashes. It calls two hooks:

```c
int jt_mac_sign(enum jt_token_alg alg, const struct jt_key *key,
                const uint8_t *msg, uint32_t mlen, uint8_t *mac);
int jt_mac_verify(enum jt_token_alg alg, const struct jt_key *key,
                  const uint8_t *msg, uint32_t mlen,
                  const uint8_t *mac, uint32_t maclen);
```

Define them yourself, or render a backend by including
`jsmn_token_crypto.c` and choosing one with `--global token_crypto=NAME`:

| `token_crypto` | Library | `jt_key.data` |
|----------------|---------|---------------|
| `psa` | PSA Crypto: Mbed TLS 3.x and 4.x, TF-PSA-Crypto, TF-M | Points at the `psa_key_id_t` of an HMAC key, so the key stays in the keystore. |
| `mbedtls` | Mbed TLS message-digest API (2.x, 3.x) | The key bytes. |
| `openssl` | OpenSSL | The key bytes. |

`jt_mac_verify` is a hook of its own so that the comparison is the
backend's: PSA compares inside the keystore, and the other two use
`jt_ct_equal`, a constant-time comparison the runtime provides.
