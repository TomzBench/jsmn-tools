#ifndef JSMN_TOOLS_TOKEN_H
#define JSMN_TOOLS_TOKEN_H

#include "runtime.h"
#include <stdint.h>

/* ── Signed tokens (JWS compact serialization, RFC 7515) ───────────── */
/*                                                                       */
/*   base64url(header) . base64url(claims) . base64url(mac)              */
/*                                                                       */
/* The claims are a schema like any other, so they are encoded and       */
/* decoded by the generated tables. This runtime adds the framing and    */
/* calls out to two hooks for the message authentication code. It keeps  */
/* no state and allocates nothing: the caller owns every buffer.         */

/* ── Error codes: continue enum jt_err below the encode range ──────── */

// clang-format off
enum jt_token_err {
    JT_ERR_TOKEN_FORMAT    = -64, /* not three base64url segments           */
    JT_ERR_TOKEN_HEADER    = -65, /* header is not the one this token signs */
    JT_ERR_TOKEN_SIGNATURE = -66, /* mac does not match                     */
    JT_ERR_TOKEN_EXPIRED   = -67, /* now is at or past the exp claim        */
    JT_ERR_TOKEN_NOT_YET   = -68, /* now is before the nbf claim            */
    JT_ERR_TOKEN_CRYPTO    = -69, /* the crypto hook failed                 */
};

enum jt_token_alg {
    JT_ALG_HS256 = 0,
    JT_ALG_HS384 = 1,
    JT_ALG_HS512 = 2,
};

#define JT_TOKEN_MAC_MAX 64 /* HS512 */

/* Unpadded base64url length of n bytes, and its inverse upper bound. */
#define JT_B64URL_LEN(n)     ((((uint32_t)(n)) * 4u + 2u) / 3u)
#define JT_B64URL_DECLEN(n)  ((((uint32_t)(n)) * 3u) / 4u)
// clang-format on

/* ── Key ───────────────────────────────────────────────────────────── */
/*                                                                       */
/* Opaque to this runtime. A backend that takes raw key bytes reads      */
/* data/len; one that keeps keys in a keystore points data at its key    */
/* handle, so the key material never has to sit in application memory.   */

struct jt_key {
    const void *data;
    uint32_t    len;
};

/* ── Token descriptor (rendered, one per x-jsmn-token schema) ──────── */
/*                                                                       */
/* This is not a table entry, unlike jt_struct, jt_field and jt_array,   */
/* and the difference is deliberate:                                     */
/*                                                                       */
/*  - Schema types are tables because they refer to one another by       */
/*    index (jt_type_t) and are decoded by key. Tokens do neither: no    */
/*    token refers to another, and each generated shim names its own     */
/*    descriptor.                                                        */
/*  - A table would add a tokens pointer to jt_schemas, which every      */
/*    user of the runtime would carry, tokens or not.                    */
/*  - A descriptor nothing calls is dropped by the linker. A table       */
/*    stays whole.                                                       */
/*                                                                       */
/* What this gives up: there is no token key, so a token type cannot be  */
/* chosen at run time the way jt_decode takes a type. If a caller needs  */
/* that, switch to a table then: emit jt_token[] and a _TOKEN_KEY per    */
/* schema from the same template loop, move the header into the names    */
/* blob so the entry holds an offset and no pointer (as the tables do),  */
/* and have the keyed entry point take its scratch from the caller,      */
/* since only the typed shims know their own buffer sizes.               */

struct jt_token {
    const char *header;     // base64url of the protected header
    uint16_t    header_len; // strlen(header)
    uint8_t     alg;        // enum jt_token_alg
    uint8_t     mac_len;    // mac size in bytes
    jt_type_t   claims;     // schema type of the claims
    uint16_t    claims_len; // max encoded claims JSON
};

#ifdef __cplusplus
extern "C" {
#endif

/* ── Crypto hooks ──────────────────────────────────────────────────── */
/*                                                                       */
/* Not defined by this runtime. Render a backend (jsmn_token_crypto.c)   */
/* or define them in the application. Both return 0 on success.          */
/*                                                                       */
/* jt_mac_sign writes the full mac for alg to mac[JT_TOKEN_MAC_MAX].     */
/* jt_mac_verify returns nonzero when the mac does not match, and must   */
/* compare in constant time.                                             */

int
jt_mac_sign(enum jt_token_alg    alg,
            const struct jt_key *key,
            const uint8_t       *msg,
            uint32_t             mlen,
            uint8_t             *mac);

int
jt_mac_verify(enum jt_token_alg    alg,
              const struct jt_key *key,
              const uint8_t       *msg,
              uint32_t             mlen,
              const uint8_t       *mac,
              uint32_t             maclen);

/* Constant-time comparison for backends that compute then compare. */
int
jt_ct_equal(const uint8_t *a, const uint8_t *b, uint32_t len);

/* ── base64url (RFC 4648 §5, no padding) ───────────────────────────── */
/*                                                                       */
/* Both return the number of bytes written, or JT_ERR_BUFFER when dst    */
/* is too small. Decode is strict: any character outside the alphabet,   */
/* an impossible length, or non-zero trailing bits is                    */
/* JT_ERR_TOKEN_FORMAT. Neither writes a terminator.                     */

int
jt_b64url_encode(char *dst, uint32_t dlen, const uint8_t *src, uint32_t slen);

int
jt_b64url_decode(uint8_t *dst, uint32_t dlen, const char *src, uint32_t slen);

/* ── Sign / verify ─────────────────────────────────────────────────── */
/*                                                                       */
/* jt_token_sign encodes claims and writes a NUL-terminated token to     */
/* dst. Returns the token length (terminator excluded) or an error.      */
/* scratch holds the claims JSON and must be t->claims_len bytes.        */
/*                                                                       */
/* jt_token_verify checks the header and the mac first, and only then    */
/* decodes the claims into dst. Returns the decoder's result (> 0) or    */
/* an error; dst is not written unless the mac matched.                  */
/* scratch must be t->claims_len bytes; toks is the decoder's workspace. */

int
jt_token_sign(const struct jt_schemas *schemas,
              const struct jt_token   *t,
              char                    *dst,
              uint32_t                 dlen,
              const void              *claims,
              const struct jt_key     *key,
              uint8_t                 *scratch);

int
jt_token_verify(const struct jt_schemas *schemas,
                const struct jt_token   *t,
                void                    *dst,
                const char              *tok,
                uint32_t                 tlen,
                const struct jt_key     *key,
                uint8_t                 *scratch,
                jsmntok_t               *toks,
                uint32_t                 ntoks);

#ifdef __cplusplus
}
#endif

#endif
