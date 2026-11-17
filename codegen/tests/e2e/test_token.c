/* Signed tokens: generated sign/verify shims over the token runtime.
 *
 * The known-answer vectors and the failure cases were carried over from
 * jsmn-web-tokens (test/main.c), whose tokens were produced at jwt.io. */
#include "token_gen.h"
#include "unity.h"
#include "util.h"
#include <string.h>

void
setUp(void)
{
}

void
tearDown(void)
{
}

#define ISS "jsmn_web_token_iss"
#define SUB "jsmn_web_token_sub"
#define IAT 1580601600u
#define EXP 1580602200u
#define SECRET "unsafe_secret"

/* {"iss":"jsmn_web_token_iss","sub":"jsmn_web_token_sub",
 *  "iat":1580601600,"exp":1580602200} */
#define PAYLOAD                                                                \
    "eyJpc3MiOiJqc21uX3dlYl90b2tlbl9pc3MiLCJzdWIiOiJqc21uX3dlYl90b2tlbl9zdWIi" \
    "LCJpYXQiOjE1ODA2MDE2MDAsImV4cCI6MTU4MDYwMjIwMH0"

#define HEADER_HS256 "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
#define TOKEN_HS256                                                            \
    HEADER_HS256 "." PAYLOAD "." "mrv4Vr2tdq7W-cQAcUqvsjmj7_GvAvgJ-RgNa7HfjeQ"

#define HEADER_HS384 "eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9"
#define TOKEN_HS384                                                            \
    HEADER_HS384 "." PAYLOAD "."                                               \
    "AI-BffUT9ymD44cIvsankVLBu89weikome1o4UQTHYgwftBgSXj30uqHEU5pfGws"

#define HEADER_HS512 "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9"
#define TOKEN_HS512                                                            \
    HEADER_HS512 "." PAYLOAD "."                                               \
    "QpBq98RW3RqzhG8b4HXeTHEAybMxMTbwuT0OvyWF9XOlzHlgHLfTJ08UWgTJy7j_"         \
    "I8W8okaB6iDWvb1wUcsreA"

static const struct jt_key key = {.data = SECRET, .len = sizeof(SECRET) - 1};

static const struct web_claims claims = {
    .iss = ISS,
    .sub = SUB,
    .iat = IAT,
    .exp = EXP,
};

/* Build a correctly signed HS256 token around any payload bytes, so the
 * tests can reach what verify does after the signature has matched. */
static uint32_t
forge(char *dst, uint32_t dlen, const char *header, const void *payload,
      uint32_t plen)
{
    uint8_t  mac[JT_TOKEN_MAC_MAX];
    uint32_t pos = (uint32_t)strlen(header);
    memcpy(dst, header, pos);
    dst[pos++] = '.';
    pos += (uint32_t)jt_b64url_encode(&dst[pos], dlen - pos, payload, plen);
    TEST_ASSERT_EQUAL_INT(
        0, jt_mac_sign(JT_ALG_HS256, &key, (const uint8_t *)dst, pos, mac));
    dst[pos++] = '.';
    pos += (uint32_t)jt_b64url_encode(&dst[pos], dlen - pos, mac, 32);
    dst[pos] = '\0';
    return pos;
}

#define FORGE(dst, json) forge(dst, sizeof(dst), HEADER_HS256, json, strlen(json))

/* ── base64url ─────────────────────────────────────────────────────── */

static void
test_b64url_rfc4648_vectors(void)
{
    static const struct {
        const char *plain, *coded;
    } v[] = {
        {"", ""},           {"f", "Zg"},         {"fo", "Zm8"},
        {"foo", "Zm9v"},    {"foob", "Zm9vYg"},  {"fooba", "Zm9vYmE"},
        {"foobar", "Zm9vYmFy"},
    };
    for (uint32_t i = 0; i < ARRAY_SIZE(v); i++) {
        char    enc[16];
        uint8_t dec[16];
        int     n = jt_b64url_encode(
            enc, sizeof(enc), (const uint8_t *)v[i].plain, strlen(v[i].plain));
        TEST_ASSERT_EQUAL_INT(strlen(v[i].coded), n);
        if (n) TEST_ASSERT_EQUAL_MEMORY(v[i].coded, enc, n);
        n = jt_b64url_decode(dec, sizeof(dec), v[i].coded, strlen(v[i].coded));
        TEST_ASSERT_EQUAL_INT(strlen(v[i].plain), n);
        if (n) TEST_ASSERT_EQUAL_MEMORY(v[i].plain, dec, n);
    }
}

static void
test_b64url_uses_url_alphabet(void)
{
    static const uint8_t raw[] = {0xfb, 0xff, 0xfe};
    char                 enc[8];
    uint8_t              dec[8];
    TEST_ASSERT_EQUAL_INT(4, jt_b64url_encode(enc, sizeof(enc), raw, 3));
    TEST_ASSERT_EQUAL_MEMORY("-__-", enc, 4);
    TEST_ASSERT_EQUAL_INT(3, jt_b64url_decode(dec, sizeof(dec), "-__-", 4));
    TEST_ASSERT_EQUAL_MEMORY(raw, dec, 3);
}

static void
test_b64url_decode_is_strict(void)
{
    uint8_t dec[16];
    // clang-format off
    static const char *bad[] = {
        "Z",        /* one character encodes nothing        */
        "Zm9vY",    /* impossible length                    */
        "Zh",       /* trailing bits not zero ("Zg" is 'f') */
        "Zm9",      /* trailing bits not zero ("Zm8")       */
        "Zg==",     /* padding is not part of base64url     */
        "+/+/",     /* the base64 alphabet, not base64url   */
        "Zm 9v",    /* whitespace                           */
    };
    // clang-format on
    for (uint32_t i = 0; i < ARRAY_SIZE(bad); i++) {
        TEST_ASSERT_EQUAL_INT_MESSAGE(
            JT_ERR_TOKEN_FORMAT,
            jt_b64url_decode(dec, sizeof(dec), bad[i], strlen(bad[i])),
            bad[i]);
    }
}

static void
test_b64url_buffer_too_small(void)
{
    char    enc[3];
    uint8_t dec[2];
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_BUFFER,
        jt_b64url_encode(enc, sizeof(enc), (const uint8_t *)"foo", 3));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_BUFFER, jt_b64url_decode(dec, sizeof(dec), "Zm9v", 4));
}

/* ── Sign: known answers ───────────────────────────────────────────── */

static void
test_sign_known_answer(void)
{
    char tok[JSMN_WEB_CLAIMS_512_TOKEN_LEN + 1];
    int  n;

    n = jsmn_token_sign_web_claims(tok, sizeof(tok), &claims, &key);
    TEST_ASSERT_EQUAL_INT(strlen(TOKEN_HS256), n);
    TEST_ASSERT_EQUAL_STRING(TOKEN_HS256, tok);

    n = jsmn_token_sign_web_claims_384(
        tok, sizeof(tok), (const struct web_claims_384 *)&claims, &key);
    TEST_ASSERT_EQUAL_INT(strlen(TOKEN_HS384), n);
    TEST_ASSERT_EQUAL_STRING(TOKEN_HS384, tok);

    n = jsmn_token_sign_web_claims_512(
        tok, sizeof(tok), (const struct web_claims_512 *)&claims, &key);
    TEST_ASSERT_EQUAL_INT(strlen(TOKEN_HS512), n);
    TEST_ASSERT_EQUAL_STRING(TOKEN_HS512, tok);
}

static void
test_sign_buffer_too_small(void)
{
    char tok[sizeof(TOKEN_HS256)];
    /* One byte short of the token and its terminator */
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_BUFFER,
        jsmn_token_sign_web_claims(tok, sizeof(tok) - 1, &claims, &key));
    TEST_ASSERT_EQUAL_INT(
        strlen(TOKEN_HS256),
        jsmn_token_sign_web_claims(tok, sizeof(tok), &claims, &key));
}

static void
test_sign_longest_claims_fit_token_len(void)
{
    /* Every string at its maxLength, every integer at its widest */
    struct web_claims big = {.iat = UINT32_MAX, .exp = UINT32_MAX};
    char              tok[JSMN_WEB_CLAIMS_TOKEN_LEN + 1];
    memset(big.iss, 'i', sizeof(big.iss) - 1);
    memset(big.sub, 's', sizeof(big.sub) - 1);
    int n = jsmn_token_sign_web_claims(tok, sizeof(tok), &big, &key);
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    TEST_ASSERT_LESS_OR_EQUAL_INT(JSMN_WEB_CLAIMS_TOKEN_LEN, n);
}

/* ── Verify ────────────────────────────────────────────────────────── */

static void
test_verify_known_answer(void)
{
    struct web_claims     c256 = {0};
    struct web_claims_384 c384 = {0};
    struct web_claims_512 c512 = {0};

    TEST_ASSERT_GREATER_THAN_INT(
        0,
        jsmn_token_verify_web_claims(
            &c256, TOKEN_HS256, strlen(TOKEN_HS256), &key, IAT));
    TEST_ASSERT_EQUAL_STRING(ISS, c256.iss);
    TEST_ASSERT_EQUAL_STRING(SUB, c256.sub);
    TEST_ASSERT_EQUAL_UINT32(IAT, c256.iat);
    TEST_ASSERT_EQUAL_UINT32(EXP, c256.exp);

    TEST_ASSERT_GREATER_THAN_INT(
        0,
        jsmn_token_verify_web_claims_384(
            &c384, TOKEN_HS384, strlen(TOKEN_HS384), &key, IAT));
    TEST_ASSERT_EQUAL_STRING(SUB, c384.sub);
    TEST_ASSERT_EQUAL_UINT32(EXP, c384.exp);

    TEST_ASSERT_GREATER_THAN_INT(
        0,
        jsmn_token_verify_web_claims_512(
            &c512, TOKEN_HS512, strlen(TOKEN_HS512), &key, IAT));
    TEST_ASSERT_EQUAL_STRING(SUB, c512.sub);
    TEST_ASSERT_EQUAL_UINT32(EXP, c512.exp);
}

static void
test_verify_roundtrip(void)
{
    const struct ticket in = {.user = "installer", .role = 3};
    struct ticket       out = {0};
    char                tok[JSMN_TICKET_TOKEN_LEN + 1];
    int                 n = jsmn_token_sign_ticket(tok, sizeof(tok), &in, &key);
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    /* A token with no time claims is verified without a clock */
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_ticket(&out, tok, (uint32_t)n, &key));
    TEST_ASSERT_EQUAL_STRING("installer", out.user);
    TEST_ASSERT_EQUAL_UINT8(3, out.role);
}

static void
test_verify_fail_signature(void)
{
    struct web_claims c;
    char              tok[] = TOKEN_HS256;
    uint32_t          len = sizeof(tok) - 1;

    /* Last character of the signature */
    tok[len - 1] = tok[len - 1] == 'Q' ? 'R' : 'Q';
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_SIGNATURE,
        jsmn_token_verify_web_claims(&c, tok, len, &key, IAT));

    /* One character of the claims */
    memcpy(tok, TOKEN_HS256, sizeof(tok));
    tok[sizeof(HEADER_HS256) + 4] ^= 1;
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_SIGNATURE,
        jsmn_token_verify_web_claims(&c, tok, len, &key, IAT));

    /* A signature of the wrong size */
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_SIGNATURE,
        jsmn_token_verify_web_claims(&c, TOKEN_HS256, len - 1, &key, IAT));
}

static void
test_verify_fail_wrong_key(void)
{
    static const struct jt_key other = {.data = "unsafe_secreT", .len = 13};
    static const struct jt_key shorter = {.data = SECRET, .len = 12};
    struct web_claims          c;
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_SIGNATURE,
        jsmn_token_verify_web_claims(
            &c, TOKEN_HS256, strlen(TOKEN_HS256), &other, IAT));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_SIGNATURE,
        jsmn_token_verify_web_claims(
            &c, TOKEN_HS256, strlen(TOKEN_HS256), &shorter, IAT));
}

static void
test_verify_binary_key(void)
{
    /* A key is bytes, not a string: zeros inside it count */
    static const uint8_t       raw[] = {0x00, 0x01, 0x00, 0xff, 0x00, 0x00};
    static const struct jt_key bin = {.data = raw, .len = sizeof(raw)};
    static const struct jt_key cut = {.data = raw, .len = 1};
    const struct ticket        in = {.user = "u", .role = 1};
    struct ticket              out;
    char                       tok[JSMN_TICKET_TOKEN_LEN + 1];
    int n = jsmn_token_sign_ticket(tok, sizeof(tok), &in, &bin);
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_ticket(&out, tok, (uint32_t)n, &bin));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_SIGNATURE,
        jsmn_token_verify_ticket(&out, tok, (uint32_t)n, &cut));
}

static void
test_verify_fail_leaves_dst_untouched(void)
{
    struct web_claims c;
    struct web_claims before;
    char              tok[] = TOKEN_HS256;
    memset(&c, 0xA5, sizeof(c));
    memcpy(&before, &c, sizeof(c));
    tok[sizeof(tok) - 2] ^= 1;
    TEST_ASSERT_LESS_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, sizeof(tok) - 1, &key, IAT));
    TEST_ASSERT_EQUAL_MEMORY(&before, &c, sizeof(c));
}

static void
test_verify_fail_header(void)
{
    struct web_claims c;
    char              tok[512];
    const char       *json = "{\"iss\":\"a\",\"sub\":\"b\",\"iat\":1,\"exp\":9}";
    // clang-format off
    static const char *headers[] = {
        "eyJ0eXAiOiJKV1RYIiwiYWxnIjoiSFMyNTYifQ", /* typ JWTX, keys swapped  */
        "eyJ0eXAiOiJKIiwiYWxnIjoiSFMyNTYifQ",     /* typ J                   */
        "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9",   /* alg ES256               */
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0",    /* alg none                */
        HEADER_HS384,                              /* another token's header  */
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ",    /* ours, one short         */
    };
    // clang-format on
    for (uint32_t i = 0; i < ARRAY_SIZE(headers); i++) {
        /* Correctly signed for its header: only the header is at fault */
        uint32_t n =
            forge(tok, sizeof(tok), headers[i], json, (uint32_t)strlen(json));
        TEST_ASSERT_EQUAL_INT_MESSAGE(
            JT_ERR_TOKEN_HEADER,
            jsmn_token_verify_web_claims(&c, tok, n, &key, 1),
            headers[i]);
    }
    /* And the same claims under our header do verify */
    uint32_t n = FORGE(tok, json);
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));
}

static void
test_verify_fail_format(void)
{
    struct web_claims c;
    // clang-format off
    static const char *bad[] = {
        "",
        "no-dots-at-all",
        HEADER_HS256,
        HEADER_HS256 ".",
        HEADER_HS256 "." PAYLOAD,
        HEADER_HS256 "." PAYLOAD ".",
        HEADER_HS256 ".." "mrv4Vr2tdq7W-cQAcUqvsjmj7_GvAvgJ-RgNa7HfjeQ",
        "." PAYLOAD "." "mrv4Vr2tdq7W-cQAcUqvsjmj7_GvAvgJ-RgNa7HfjeQ",
        TOKEN_HS256 ".extra",
    };
    // clang-format on
    for (uint32_t i = 0; i < ARRAY_SIZE(bad); i++) {
        TEST_ASSERT_EQUAL_INT_MESSAGE(
            JT_ERR_TOKEN_FORMAT,
            jsmn_token_verify_web_claims(&c, bad[i], strlen(bad[i]), &key, 1),
            bad[i]);
    }
}

static void
test_verify_fail_fuzz(void)
{
    /* No single-character change and no truncation of a good token verifies */
    struct web_claims c;
    char              tok[] = TOKEN_HS256;
    uint32_t          len = sizeof(tok) - 1;
    for (uint32_t i = 0; i < len; i++) {
        char keep = tok[i];
        tok[i] = keep == 'A' ? 'B' : 'A';
        TEST_ASSERT_LESS_THAN_INT(
            0, jsmn_token_verify_web_claims(&c, tok, len, &key, IAT));
        tok[i] = keep;
    }
    for (uint32_t i = 0; i < len; i++) {
        TEST_ASSERT_LESS_THAN_INT(
            0, jsmn_token_verify_web_claims(&c, tok, i, &key, IAT));
    }
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, len, &key, IAT));
}

/* ── Verify: a good signature over bad claims ──────────────────────── */

static void
test_verify_signed_claims_too_long(void)
{
    struct web_claims c;
    char              tok[1024];
    char              json[JSMN_WEB_CLAIMS_LEN + 64];
    memset(json, ' ', sizeof(json));
    memcpy(json, "{\"iss\":\"a\",\"sub\":\"b\",\"iat\":1,\"exp\":9", 36);
    json[sizeof(json) - 1] = '}';
    uint32_t n = forge(tok, sizeof(tok), HEADER_HS256, json, sizeof(json));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_BUFFER, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));
}

static void
test_verify_signed_claims_malformed(void)
{
    struct web_claims c;
    char              tok[512];
    uint32_t          n;

    n = FORGE(tok, "{\"iss\":\"a\",\"sub\":\"b\",\"iat\":1,\"exp\":");
    TEST_ASSERT_LESS_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));

    n = FORGE(tok, "{\"iss\":\"a\",\"sub\":\"b\",\"iat\":1}");
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_REQUIRED, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));

    n = FORGE(tok, "{\"iss\":\"a\",\"sub\":\"b\",\"iat\":1,\"exp\":true}");
    TEST_ASSERT_LESS_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));

    n = FORGE(
        tok,
        "{\"iss\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"sub\":\"b\","
        "\"iat\":1,\"exp\":9}");
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_STR_LENGTH, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));

    /* Claims with a zero byte in them are data like any other */
    static const char nul[] = "{\"iss\":\"a\0b\",\"sub\":\"b\",\"iat\":1,\"exp\":9}";
    n = forge(tok, sizeof(tok), HEADER_HS256, nul, sizeof(nul) - 1);
    TEST_ASSERT_LESS_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, n, &key, 1));
}

/* ── Verify: time claims ───────────────────────────────────────────── */

static void
test_verify_expiry(void)
{
    struct web_claims c;
    uint32_t          len = strlen(TOKEN_HS256);
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, TOKEN_HS256, len, &key, 0));
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, TOKEN_HS256, len, &key, EXP - 1));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_EXPIRED,
        jsmn_token_verify_web_claims(&c, TOKEN_HS256, len, &key, EXP));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_EXPIRED,
        jsmn_token_verify_web_claims(&c, TOKEN_HS256, len, &key, UINT32_MAX));
}

static void
test_verify_window(void)
{
    /* nbf is renamed in C (not_before) and still enforced */
    const struct window in = {.not_before = 100, .exp = 200};
    struct window       out;
    char                tok[JSMN_WINDOW_TOKEN_LEN + 1];
    int                 n = jsmn_token_sign_window(tok, sizeof(tok), &in, &key);
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_NOT_YET,
        jsmn_token_verify_window(&out, tok, (uint32_t)n, &key, 99));
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_window(&out, tok, (uint32_t)n, &key, 100));
    TEST_ASSERT_GREATER_THAN_INT(
        0, jsmn_token_verify_window(&out, tok, (uint32_t)n, &key, 199));
    TEST_ASSERT_EQUAL_INT(
        JT_ERR_TOKEN_EXPIRED,
        jsmn_token_verify_window(&out, tok, (uint32_t)n, &key, 200));
    TEST_ASSERT_EQUAL_UINT32(100, out.not_before);
}

/* ── Tokens are not interchangeable ────────────────────────────────── */

static void
test_verify_other_token_type(void)
{
    /* Same header and key, different claims: the schema rejects it */
    const struct ticket in = {.user = "u", .role = 1};
    struct web_claims   c;
    char                tok[JSMN_TICKET_TOKEN_LEN + 1];
    int                 n = jsmn_token_sign_ticket(tok, sizeof(tok), &in, &key);
    TEST_ASSERT_GREATER_THAN_INT(0, n);
    TEST_ASSERT_LESS_THAN_INT(
        0, jsmn_token_verify_web_claims(&c, tok, (uint32_t)n, &key, 1));
}

int
main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_b64url_rfc4648_vectors);
    RUN_TEST(test_b64url_uses_url_alphabet);
    RUN_TEST(test_b64url_decode_is_strict);
    RUN_TEST(test_b64url_buffer_too_small);
    RUN_TEST(test_sign_known_answer);
    RUN_TEST(test_sign_buffer_too_small);
    RUN_TEST(test_sign_longest_claims_fit_token_len);
    RUN_TEST(test_verify_known_answer);
    RUN_TEST(test_verify_roundtrip);
    RUN_TEST(test_verify_fail_signature);
    RUN_TEST(test_verify_fail_wrong_key);
    RUN_TEST(test_verify_binary_key);
    RUN_TEST(test_verify_fail_leaves_dst_untouched);
    RUN_TEST(test_verify_fail_header);
    RUN_TEST(test_verify_fail_format);
    RUN_TEST(test_verify_fail_fuzz);
    RUN_TEST(test_verify_signed_claims_too_long);
    RUN_TEST(test_verify_signed_claims_malformed);
    RUN_TEST(test_verify_expiry);
    RUN_TEST(test_verify_window);
    RUN_TEST(test_verify_other_token_type);
    return UNITY_END();
}
