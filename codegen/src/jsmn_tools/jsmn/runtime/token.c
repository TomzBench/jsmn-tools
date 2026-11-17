#include "token.h"
#include "jsmn.h"
#include "runtime.h"
#include <stdint.h>
#include <string.h>

/* ── base64url ─────────────────────────────────────────────────────── */

static const char b64url_alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

static int
b64url_value(char c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '-') return 62;
    if (c == '_') return 63;
    return -1;
}

int
jt_b64url_encode(char *dst, uint32_t dlen, const uint8_t *src, uint32_t slen)
{
    uint32_t n = JT_B64URL_LEN(slen), i = 0, o = 0;
    if (dlen < n) return JT_ERR_BUFFER;
    for (; i + 2 < slen; i += 3) {
        uint32_t v = (uint32_t)src[i] << 16 | (uint32_t)src[i + 1] << 8 |
                     src[i + 2];
        dst[o++] = b64url_alphabet[v >> 18];
        dst[o++] = b64url_alphabet[(v >> 12) & 63];
        dst[o++] = b64url_alphabet[(v >> 6) & 63];
        dst[o++] = b64url_alphabet[v & 63];
    }
    if (slen - i == 1) {
        uint32_t v = (uint32_t)src[i] << 16;
        dst[o++] = b64url_alphabet[v >> 18];
        dst[o++] = b64url_alphabet[(v >> 12) & 63];
    } else if (slen - i == 2) {
        uint32_t v = (uint32_t)src[i] << 16 | (uint32_t)src[i + 1] << 8;
        dst[o++] = b64url_alphabet[v >> 18];
        dst[o++] = b64url_alphabet[(v >> 12) & 63];
        dst[o++] = b64url_alphabet[(v >> 6) & 63];
    }
    return (int)o;
}

int
jt_b64url_decode(uint8_t *dst, uint32_t dlen, const char *src, uint32_t slen)
{
    uint32_t rem = slen & 3u, n = JT_B64URL_DECLEN(slen), acc = 0, o = 0;
    if (rem == 1) return JT_ERR_TOKEN_FORMAT;
    if (dlen < n) return JT_ERR_BUFFER;
    for (uint32_t i = 0; i < slen; i++) {
        int v = b64url_value(src[i]);
        if (v < 0) return JT_ERR_TOKEN_FORMAT;
        acc = acc << 6 | (uint32_t)v;
        if ((i & 3u) == 3u) {
            dst[o++] = (uint8_t)(acc >> 16);
            dst[o++] = (uint8_t)(acc >> 8);
            dst[o++] = (uint8_t)acc;
            acc = 0;
        }
    }
    /* A tail of 2 or 3 characters carries 4 or 2 bits that encode nothing.
     * They must be zero, or two different strings would decode alike. */
    if (rem == 2) {
        if (acc & 0xFu) return JT_ERR_TOKEN_FORMAT;
        dst[o++] = (uint8_t)(acc >> 4);
    } else if (rem == 3) {
        if (acc & 0x3u) return JT_ERR_TOKEN_FORMAT;
        dst[o++] = (uint8_t)(acc >> 10);
        dst[o++] = (uint8_t)(acc >> 2);
    }
    return (int)o;
}

int
jt_ct_equal(const uint8_t *a, const uint8_t *b, uint32_t len)
{
    volatile uint8_t diff = 0;
    for (uint32_t i = 0; i < len; i++) diff |= (uint8_t)(a[i] ^ b[i]);
    return diff == 0;
}

/* ── Sign ──────────────────────────────────────────────────────────── */

int
jt_token_sign(const struct jt_schemas *schemas,
              const struct jt_token   *t,
              char                    *dst,
              uint32_t                 dlen,
              const void              *claims,
              const struct jt_key     *key,
              uint8_t                 *scratch)
{
    uint8_t  mac[JT_TOKEN_MAC_MAX];
    uint32_t pos = t->header_len;
    int      n;

    n = jt_encode(schemas, scratch, t->claims_len, claims, t->claims);
    if (n < 0) return n;

    /* header . claims . mac NUL */
    if (dlen < pos + 1 + JT_B64URL_LEN(n) + 1 + JT_B64URL_LEN(t->mac_len) + 1) {
        return JT_ERR_BUFFER;
    }
    memcpy(dst, t->header, pos);
    dst[pos++] = '.';
    pos += (uint32_t)jt_b64url_encode(&dst[pos], dlen - pos, scratch, n);

    if (jt_mac_sign(t->alg, key, (const uint8_t *)dst, pos, mac)) {
        return JT_ERR_TOKEN_CRYPTO;
    }
    dst[pos++] = '.';
    pos += (uint32_t)jt_b64url_encode(&dst[pos], dlen - pos, mac, t->mac_len);
    dst[pos] = '\0';
    return (int)pos;
}

/* ── Verify ────────────────────────────────────────────────────────── */

int
jt_token_verify(const struct jt_schemas *schemas,
                const struct jt_token   *t,
                void                    *dst,
                const char              *tok,
                uint32_t                 tlen,
                const struct jt_key     *key,
                uint8_t                 *scratch,
                jsmntok_t               *toks,
                uint32_t                 ntoks)
{
    uint8_t     mac[JT_TOKEN_MAC_MAX];
    const char *dot1, *dot2, *body, *sig;
    uint32_t    body_len, sig_len, signed_len;
    int         n;

    /* Exactly three segments, none of them empty. */
    dot1 = memchr(tok, '.', tlen);
    if (!dot1 || dot1 == tok) return JT_ERR_TOKEN_FORMAT;
    body = dot1 + 1;
    dot2 = memchr(body, '.', tlen - (uint32_t)(body - tok));
    if (!dot2 || dot2 == body) return JT_ERR_TOKEN_FORMAT;
    sig = dot2 + 1;
    body_len = (uint32_t)(dot2 - body);
    sig_len = tlen - (uint32_t)(sig - tok);
    signed_len = (uint32_t)(dot2 - tok);
    if (!sig_len || memchr(sig, '.', sig_len)) return JT_ERR_TOKEN_FORMAT;

    /* The header this token type signs is a constant, so it is compared
     * and never parsed: a token cannot choose its own algorithm. */
    if ((uint32_t)(dot1 - tok) != t->header_len ||
        memcmp(tok, t->header, t->header_len)) {
        return JT_ERR_TOKEN_HEADER;
    }

    /* Authenticate before anything is decoded from the claims. */
    if (sig_len != JT_B64URL_LEN(t->mac_len)) return JT_ERR_TOKEN_SIGNATURE;
    n = jt_b64url_decode(mac, sizeof(mac), sig, sig_len);
    if (n != t->mac_len) return JT_ERR_TOKEN_SIGNATURE;
    if (jt_mac_verify(
            t->alg, key, (const uint8_t *)tok, signed_len, mac, t->mac_len)) {
        return JT_ERR_TOKEN_SIGNATURE;
    }

    n = jt_b64url_decode(scratch, t->claims_len, body, body_len);
    if (n < 0) return n;
    return jt_decode(schemas, toks, ntoks, dst, t->claims, (char *)scratch, n);
}
