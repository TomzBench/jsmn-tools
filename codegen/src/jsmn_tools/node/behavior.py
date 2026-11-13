from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Identity = Callable[[Any], str]


@dataclass(frozen=True)
class Behavior:
    """How the collection at one location of a draft behaves.

    ``identity`` says the entries of the collection are identified things:
    it maps a list item, or a dict key, to the string that identifies it.
    Two entries with one identity are the same thing, so a join compares
    them whole and reports a conflict when they differ; it never merges
    into them. A list with an identity is also kept sorted by it.

    Without an identity a dict is merged key by key and a list position by
    position. A conflict keeps the first value seen.
    """

    identity: Identity | None = None


_NO_BHV = Behavior()

# A map of named definitions: the key is the name.
NAMED = Behavior(identity=str)


def canonical(x: Any) -> str:
    """Canonical sort key for any JSON value."""
    return json.dumps(x, sort_keys=True)


def identity_key(*fields: str) -> Identity:
    """Create a sort key from identity fields of a dict."""
    def key(x: Any) -> str:
        if isinstance(x, dict):
            return "\x00".join(x.get(f, "") for f in fields)
        return canonical(x)

    return key


def sort_set(arr: list) -> list:
    """Canonical sort for set-like arrays.

    Handles primitives, objects, mixed types.
    For: required, enum, type, tags, examples,
    allOf, oneOf, anyOf, security."""
    return sorted(arr, key=canonical)


def sort_set_by(arr: list[dict], *keys: str) -> list[dict]:
    """Sort object arrays by identity key fields.
    For: parameters (name, in)."""
    return sorted(arr, key=identity_key(*keys))
