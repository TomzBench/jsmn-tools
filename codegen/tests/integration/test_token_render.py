"""Signed tokens: the ``token`` filter and the templates built on it."""

from pathlib import Path

import pytest
from jinja2 import Environment
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from ruamel.yaml import YAML

from jsmn_tools.jsmn.descriptor import StructDescriptor
from jsmn_tools.jsmn.filters import b64url, b64url_len
from jsmn_tools.jsmn.prepare import bundle_codegen, extend_codegen

yaml = YAML(typ="safe")
FIXTURE = Path(__file__).parent.parent / "fixtures" / "token" / "session.yaml"

# {"alg":"HS256","typ":"JWT"}, the header every JWT library emits for HS256
HEADER_HS256 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"


def _env(spec: dict) -> Environment:
    resource = Resource.from_contents(spec, default_specification=DRAFT202012)
    resolver, bundle = bundle_codegen([resource] @ Registry())
    env = Environment(
        keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True
    )
    extend_codegen(env, bundle, resolver=resolver, prefix="jsmn_")
    return env


def _spec(token) -> dict:
    return {
        "openapi": "3.1.0",
        "$id": "forge://test/token/v0",
        "info": {"title": "t", "version": "0"},
        "components": {
            "schemas": {
                "claims": {
                    "type": "object",
                    "x-jsmn-type": "claims",
                    "x-jsmn-token": token,
                    "required": ["exp"],
                    "properties": {
                        "exp": {"type": "integer", "format": "uint32"}
                    },
                }
            }
        },
    }


@pytest.fixture()
def env() -> Environment:
    return _env(yaml.load(FIXTURE))


def _tokens(env: Environment) -> dict[str, dict | None]:
    token = env.filters["token"]
    return {
        d.ctype.name: token(d)
        for d in env.globals["descriptors"]
        if isinstance(d, StructDescriptor)
    }


def test_b64url_has_no_padding_and_uses_the_url_alphabet() -> None:
    assert b64url("f") == "Zg"
    assert b64url("fo") == "Zm8"
    assert b64url("foobar") == "Zm9vYmFy"
    assert b64url(bytes([0xFB, 0xFF, 0xFE])) == "-__-"
    assert b64url('{"alg":"HS256","typ":"JWT"}') == HEADER_HS256


@pytest.mark.parametrize("n", range(0, 70))
def test_b64url_len_matches_the_encoder(n: int) -> None:
    assert b64url_len(n) == len(b64url(bytes(n)))


def test_token_describes_each_declared_token(env: Environment) -> None:
    tokens = _tokens(env)
    assert tokens["plain"] is None
    assert tokens["web_claims"]["header"] == HEADER_HS256
    assert tokens["web_claims"]["mac_len"] == 32
    assert tokens["web_claims_384"]["mac_len"] == 48
    assert tokens["web_claims_512"]["mac_len"] == 64
    # x-jsmn-token: {} takes the default algorithm
    assert tokens["window"]["alg"] == "HS256"


def test_token_len_is_the_three_segments_and_two_dots(env: Environment) -> None:
    by_name = {
        d.ctype.name: d
        for d in env.globals["descriptors"]
        if isinstance(d, StructDescriptor)
    }
    t = env.filters["token"](by_name["web_claims"])
    claims = b64url_len(by_name["web_claims"].encode_len)
    assert t["len"] == len(HEADER_HS256) + 1 + claims + 1 + b64url_len(32)


def test_token_enforces_only_required_time_claims(env: Environment) -> None:
    tokens = _tokens(env)
    assert (tokens["web_claims"]["exp"], tokens["web_claims"]["nbf"]) == (
        "exp",
        None,
    )
    assert (tokens["ticket"]["exp"], tokens["ticket"]["nbf"]) == (None, None)
    # The C name of a renamed claim is the one the check reads
    assert tokens["window"]["nbf"] == "not_before"


def test_token_optional_time_claim_is_not_enforced() -> None:
    spec = _spec({"alg": "HS256"})
    spec["components"]["schemas"]["claims"]["required"] = []
    assert _tokens(_env(spec))["claims"]["exp"] is None


def test_token_rejects_an_unknown_algorithm() -> None:
    with pytest.raises(ValueError, match="alg 'RS256' is not supported"):
        _tokens(_env(_spec({"alg": "RS256"})))


def test_token_rejects_a_declaration_that_is_not_a_mapping() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        _tokens(_env(_spec("HS256")))


def test_render_token_generated_decl(env: Environment, snapshot) -> None:
    tpl = "{% include 'jsmn_token_generated.h' %}"
    assert env.from_string(tpl).render() == snapshot


def test_render_token_generated_impl(env: Environment, snapshot) -> None:
    tpl = "{% include 'jsmn_token_generated.c' %}"
    assert env.from_string(tpl).render() == snapshot


def test_render_verify_takes_a_clock_only_with_time_claims(
    env: Environment,
) -> None:
    out = env.from_string("{% include 'jsmn_token_generated.h' %}").render()
    protos = {
        p.split("(")[0].split()[-1]: p
        for p in out.split(";")
        if "token_verify" in p
    }
    assert "uint32_t now" in protos["jsmn_token_verify_web_claims"]
    assert "uint32_t now" in protos["jsmn_token_verify_window"]
    assert "uint32_t now" not in protos["jsmn_token_verify_ticket"]


def test_render_no_token_code_without_a_declaration() -> None:
    spec = _spec({"alg": "HS256"})
    del spec["components"]["schemas"]["claims"]["x-jsmn-token"]
    env = _env(spec)
    for name in ("jsmn_token_generated.h", "jsmn_token_generated.c"):
        out = env.from_string("{% include '" + name + "' %}").render()
        assert out.strip() == ""


@pytest.mark.parametrize(
    ("backend", "marker"),
    [
        ("psa", "psa_mac_verify"),
        ("mbedtls", "mbedtls_md_hmac"),
        ("openssl", "EVP_sha256"),
    ],
)
def test_render_crypto_backend(
    env: Environment, backend: str, marker: str
) -> None:
    env.globals["token_crypto"] = backend
    out = env.from_string("{% include 'jsmn_token_crypto.c' %}").render()
    assert marker in out
    assert "jt_mac_sign(" in out and "jt_mac_verify(" in out
    assert "#error" not in out


def test_render_crypto_backend_must_be_chosen(env: Environment) -> None:
    out = env.from_string("{% include 'jsmn_token_crypto.c' %}").render()
    assert "#error" in out
    assert "jt_mac_sign(" not in out
