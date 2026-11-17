{# --- Crypto backend for signed tokens: defines jt_mac_sign/jt_mac_verify.
       Select with --global token_crypto=psa|mbedtls|openssl. An application
       that brings its own crypto renders none of this and defines the two
       hooks itself. --- #}
{% if token_crypto == "psa" %}
/* PSA Crypto (Mbed TLS 3.x/4.x, TF-PSA-Crypto, TF-M). jt_key.data points at
 * the psa_key_id_t of an HMAC key the application imported or generated, so
 * the key bytes stay in the keystore. Call psa_crypto_init() first. */
#include <psa/crypto.h>

static psa_algorithm_t
jt_psa_alg(enum jt_token_alg alg)
{
    switch (alg) {
        case JT_ALG_HS256: return PSA_ALG_HMAC(PSA_ALG_SHA_256);
        case JT_ALG_HS384: return PSA_ALG_HMAC(PSA_ALG_SHA_384);
        case JT_ALG_HS512: return PSA_ALG_HMAC(PSA_ALG_SHA_512);
    }
    return PSA_ALG_NONE;
}

int
jt_mac_sign(enum jt_token_alg    alg,
            const struct jt_key *key,
            const uint8_t       *msg,
            uint32_t             mlen,
            uint8_t             *mac)
{
    size_t n = 0;
    return psa_mac_compute(*(const psa_key_id_t *)key->data, jt_psa_alg(alg),
                           msg, mlen, mac, JT_TOKEN_MAC_MAX, &n) == PSA_SUCCESS
               ? 0
               : -1;
}

int
jt_mac_verify(enum jt_token_alg    alg,
              const struct jt_key *key,
              const uint8_t       *msg,
              uint32_t             mlen,
              const uint8_t       *mac,
              uint32_t             maclen)
{
    return psa_mac_verify(*(const psa_key_id_t *)key->data, jt_psa_alg(alg),
                          msg, mlen, mac, maclen) == PSA_SUCCESS
               ? 0
               : -1;
}
{% elif token_crypto in ("mbedtls", "openssl") %}
{% if token_crypto == "mbedtls" %}
/* Mbed TLS message-digest API (2.x and 3.x; Mbed TLS 4 made it private,
 * use the psa backend there). jt_key holds the raw key bytes. */
#include <mbedtls/md.h>

static int
jt_hmac(enum jt_token_alg    alg,
        const struct jt_key *key,
        const uint8_t       *msg,
        uint32_t             mlen,
        uint8_t             *mac)
{
    mbedtls_md_type_t type;
    switch (alg) {
        case JT_ALG_HS256: type = MBEDTLS_MD_SHA256; break;
        case JT_ALG_HS384: type = MBEDTLS_MD_SHA384; break;
        case JT_ALG_HS512: type = MBEDTLS_MD_SHA512; break;
        default: return -1;
    }
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(type);
    if (!info) return -1;
    return mbedtls_md_hmac(info, key->data, key->len, msg, mlen, mac) ? -1 : 0;
}
{% else %}
/* OpenSSL. jt_key holds the raw key bytes. */
#include <openssl/evp.h>
#include <openssl/hmac.h>

static int
jt_hmac(enum jt_token_alg    alg,
        const struct jt_key *key,
        const uint8_t       *msg,
        uint32_t             mlen,
        uint8_t             *mac)
{
    const EVP_MD *md;
    unsigned int  n = 0;
    switch (alg) {
        case JT_ALG_HS256: md = EVP_sha256(); break;
        case JT_ALG_HS384: md = EVP_sha384(); break;
        case JT_ALG_HS512: md = EVP_sha512(); break;
        default: return -1;
    }
    return HMAC(md, key->data, (int)key->len, msg, mlen, mac, &n) ? 0 : -1;
}
{% endif %}

static uint32_t
jt_mac_len(enum jt_token_alg alg)
{
    switch (alg) {
        case JT_ALG_HS256: return 32;
        case JT_ALG_HS384: return 48;
        case JT_ALG_HS512: return 64;
    }
    return 0;
}

int
jt_mac_sign(enum jt_token_alg    alg,
            const struct jt_key *key,
            const uint8_t       *msg,
            uint32_t             mlen,
            uint8_t             *mac)
{
    return jt_hmac(alg, key, msg, mlen, mac);
}

int
jt_mac_verify(enum jt_token_alg    alg,
              const struct jt_key *key,
              const uint8_t       *msg,
              uint32_t             mlen,
              const uint8_t       *mac,
              uint32_t             maclen)
{
    uint8_t expect[JT_TOKEN_MAC_MAX];
    if (maclen != jt_mac_len(alg)) return -1;
    if (jt_hmac(alg, key, msg, mlen, expect)) return -1;
    return jt_ct_equal(expect, mac, maclen) ? 0 : -1;
}
{% else %}
#error "jsmn_token_crypto.c: set --global token_crypto=psa|mbedtls|openssl"
{% endif %}
