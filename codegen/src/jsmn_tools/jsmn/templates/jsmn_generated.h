{% for d in descriptors if d is public %}
{% set table = d | table_kind %}
#define {{ d | type_prefix_or(prefix) | upper }}{{ d | nameify | upper }}_KEY {{ table }}({{ d.key.pos }})
#define {{ d | type_prefix_or(prefix) | upper }}{{ d | nameify | upper }}_LEN ({{ d.encode_len }})
#define {{ d | type_prefix_or(prefix) | upper }}{{ d | nameify | upper }}_NTOKS ({{ d.ntoks }})
{% endfor %}

{# --- The C struct/union/enum/typedef declarations --- #}
{% for decl in declarations %}
{% if decl is struct_decl %}
{% set rename_all = decl | location("x-jsmn-rename-all") %}
struct {{ decl.ctype.name }} {
{% for f in decl.fields %}
{% set c_name = (decl | location("properties", f.name, "x-jsmn-rename")) or (f.name | caseify(rename_all) if rename_all else f.name) %}
{% set t = f.ctype | raw %}
    {{ (t | qualifier ~ ' ' ~ t.name) | trim }} {{ c_name }}{{ t.dims | dimensions }};
{% endfor %}
};
{% elif decl is union_decl %}
union {{ decl.ctype.name }} {
{% for v in decl.variants %}
{% set t = v.ctype | raw %}
    {{ (t | qualifier ~ ' ' ~ t.name) | trim }} {{ v.name }}{{ t.dims | dimensions }};
{% endfor %}
};
{% elif decl is array_decl %}
{% set t = decl.elem | raw %}
typedef {{ (t | qualifier ~ ' ' ~ t.name) | trim }} {{ decl.ctype.name }}[{{ decl.max }}]{{ t.dims | dimensions }};
{% endif +%}
{% endfor -%}

{# --- Polymorphic encode/decode --- #}
int32_t {{ prefix }}decode(
    jsmntok_t *toks,
    uint32_t ntoks,
    void *dst,
    jt_type_t type,
    const char *src,
    uint32_t slen);

int32_t {{ prefix }}encode(
    uint8_t *dst,
    uint32_t dlen,
    const void *src,
    jt_type_t type);

int32_t {{ prefix }}pack(
    uint8_t *dst,
    uint32_t dlen,
    const struct jt_part *parts,
    uint32_t n);

int32_t {{ prefix }}unpack(
    jsmntok_t *toks,
    uint32_t ntoks,
    const char *src,
    uint32_t slen,
    struct jt_part *parts,
    uint32_t n);

{# --- Prototypes (extern) or inline bodies --- #}
{% for d in descriptors if d is public %}
{% set mode = d | shim_mode_or(default_shim_mode) %}
{% set name = (d | type_prefix_or(prefix)) | upper ~ (d | nameify) | upper -%}
{% set ctype_decl = (d.ctype | qualifier ~ ' ' ~ d.ctype.name) | trim -%}
{% set decode = (d | method_name("decode", fallback_prefix=prefix)) -%}
{% set encode = (d | method_name("encode", fallback_prefix=prefix)) -%}
{% if mode == "extern" %}
int32_t {{ decode }}_tok(
    {{ ctype_decl }} *dst,
    const char *src,
    uint32_t slen,
    jsmntok_t *toks,
    uint32_t ntoks);

int32_t {{ decode }}(
    {{ ctype_decl }} *dst,
    const char *src,
    uint32_t slen);

int32_t {{ encode }}(
    uint8_t *dst,
    uint32_t dlen,
    const {{ ctype_decl }} *src);

{% elif mode == "inline" %}
static inline int32_t
{{ decode }}_tok(
    {{ ctype_decl }} *dst,
    const char *src,
    uint32_t slen,
    jsmntok_t *toks,
    uint32_t ntoks)
{
    return {{ prefix }}decode(toks, ntoks, dst, {{ name }}_KEY, src, slen);
}

static inline int32_t
{{ decode }}(
    {{ ctype_decl }} *dst,
    const char *src,
    uint32_t slen)
{
    jsmntok_t toks[{{ name }}_NTOKS];
    return {{ decode }}_tok(dst, src, slen, toks, {{ name }}_NTOKS);
}

static inline int32_t
{{ encode }}(
    uint8_t *dst,
    uint32_t dlen,
    const {{ ctype_decl }} *src)
{
	return {{ prefix }}encode(dst, dlen, src, {{ name }}_KEY);
}

{% endif %}
{% endfor %}
