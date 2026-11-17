{# --- Signed tokens. Render after jsmn_generated.c, in the same file: the
       shims read the schema tables that file keeps static.

       Each token gets a descriptor of its own here, not a row in a table
       like the structs, fields and arrays above. That is on purpose; the
       reasons, and what to change if tokens ever need to be picked by key
       at run time, are with struct jt_token in token.h. --- #}
{% for d in descriptors if d is public and d | token %}
{% set t = d | token %}
{% set name = (d | type_prefix_or(prefix)) | upper ~ (d | nameify) | upper -%}
{% set ctype_decl = (d.ctype | qualifier ~ ' ' ~ d.ctype.name) | trim -%}
{% set sign = (d | method_name("token_sign", fallback_prefix=prefix)) -%}
{% set verify = (d | method_name("token_verify", fallback_prefix=prefix)) -%}
{% set desc = (d | method_name("token", fallback_prefix=prefix)) -%}

static const struct jt_token {{ desc }} = {
    .header     = "{{ t.header }}",
    .header_len = {{ t.header | length }},
    .alg        = JT_ALG_{{ t.alg }},
    .mac_len    = {{ t.mac_len }},
    .claims     = {{ name }}_KEY,
    .claims_len = {{ name }}_LEN,
};

int32_t
{{ sign }}(
    char *dst,
    uint32_t dlen,
    const {{ ctype_decl }} *claims,
    const struct jt_key *key)
{
    uint8_t scratch[{{ name }}_LEN];
    return jt_token_sign(
        &{{ prefix }}schemas, &{{ desc }}, dst, dlen, claims, key, scratch);
}

int32_t
{{ verify }}(
    {{ ctype_decl }} *dst,
    const char *tok,
    uint32_t tlen,
    const struct jt_key *key{% if t.exp or t.nbf %},
    uint32_t now{% endif %})
{
    uint8_t scratch[{{ name }}_LEN];
    jsmntok_t toks[{{ name }}_NTOKS];
    int32_t n = jt_token_verify(
        &{{ prefix }}schemas, &{{ desc }}, dst, tok, tlen, key, scratch,
        toks, {{ name }}_NTOKS);
    if (n < 0) return n;
{% if t.nbf %}
    if ((int64_t)now < (int64_t)dst->{{ t.nbf }}) return JT_ERR_TOKEN_NOT_YET;
{% endif %}
{% if t.exp %}
    if ((int64_t)now >= (int64_t)dst->{{ t.exp }}) return JT_ERR_TOKEN_EXPIRED;
{% endif %}
    return n;
}
{% endfor %}
