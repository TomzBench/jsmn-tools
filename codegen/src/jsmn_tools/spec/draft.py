from typing import Any

from jsmn_tools.node import ObjectNode

from .asyncapi_3_0 import obj_root as ASYNCAPI_3_0
from .openapi_3_1 import obj_root as OPENAPI_3_1

DRAFTS = {"openapi": OPENAPI_3_1, "asyncapi": ASYNCAPI_3_0}


def parse_draft(content: Any) -> ObjectNode | None:
    return next((d for k, d in DRAFTS.items() if k in content), None)


def parse_draft_name(content: Any) -> str:
    return next((k for k in DRAFTS if k in content), "jsonschema")


def split_draft(*content: Any) -> tuple[list[Any], list[Any], list[Any]]:
    parsed = {OPENAPI_3_1: [], ASYNCAPI_3_0: [], None: []}
    for c in content:
        parsed[parse_draft(c)].append(c)
    return parsed[OPENAPI_3_1], parsed[ASYNCAPI_3_0], parsed[None]
