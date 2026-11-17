{# --- Signed tokens: one sign/verify pair per x-jsmn-token schema --- #}
{% for d in descriptors if d is public and d | token %}
{% set t = d | token %}
{% set name = (d | type_prefix_or(prefix)) | upper ~ (d | nameify) | upper -%}
{% set ctype_decl = (d.ctype | qualifier ~ ' ' ~ d.ctype.name) | trim -%}
{% set sign = (d | method_name("token_sign", fallback_prefix=prefix)) -%}
{% set verify = (d | method_name("token_verify", fallback_prefix=prefix)) -%}
/* Longest {{ t.alg }} token of {{ ctype_decl }}, terminator excluded */
#define {{ name }}_TOKEN_LEN ({{ t.len }})

int32_t {{ sign }}(
    char *dst,
    uint32_t dlen,
    const {{ ctype_decl }} *claims,
    const struct jt_key *key);

int32_t {{ verify }}(
    {{ ctype_decl }} *dst,
    const char *tok,
    uint32_t tlen,
    const struct jt_key *key{% if t.exp or t.nbf %},
    uint32_t now{% endif %});

{% endfor %}
