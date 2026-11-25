from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Protocol

from .behavior import _NO_BHV, Behavior


class Node[K: str](Protocol):
    @property
    def kind(self) -> K: ...
    @property
    def opaque(self) -> bool: ...
    def child(self, prop: str) -> tuple[Node[Any], Behavior]: ...


class SchemaKind(StrEnum):
    SCHEMA = "schema"
    SCHEMA_ENTER = "schema_enter"
    MAP_SCHEMA = "map_schema"
    MAP_SCHEMA_ENTER = "map_schema_enter"
    MAP_STRING_SET = "map_string_set"
    LIST_SCHEMA = "list_schema"


class DataNode:
    opaque = True

    @property
    def kind(self) -> Literal["data"]:
        return "data"

    def child(self, prop: str) -> tuple[Node[Any], Behavior]:
        return (self, _NO_BHV)

    def __repr__(self) -> str:
        return "data"


# Module-level singleton: the universal trap state
data = DataNode()


class MapNode[E: str]:
    """A collection of one kind of thing: a map or a list.

    Every entry leads to the same child, whatever its key or its index.
    """

    opaque = False

    def __init__(self, kind: E) -> None:
        self._kind = kind
        self._child: Node[Any] | None = None
        self._behavior: Behavior = _NO_BHV

    @property
    def kind(self) -> E:
        return self._kind

    def configure(
        self,
        child: Node[Any],
        behavior: Behavior = _NO_BHV,
    ) -> None:
        self._child = child
        self._behavior = behavior

    def child(self, prop: str) -> tuple[Node[Any], Behavior]:
        assert self._child is not None, f"{self._kind} not configured"
        return (self._child, self._behavior)

    def __repr__(self) -> str:
        return str(self._kind)


class ObjectNode[E: str]:
    opaque = False

    def __init__(self, kind: E) -> None:
        self._kind = kind
        self._table: dict[str, tuple[Node[Any], Behavior]] = {}

    @property
    def kind(self) -> E:
        return self._kind

    def configure(self, table: dict[str, tuple[Node[Any], Behavior]]) -> None:
        self._table = table

    def child(self, prop: str) -> tuple[Node[Any], Behavior]:
        return self._table.get(prop, (data, _NO_BHV))

    def __repr__(self) -> str:
        return str(self._kind)


class SchemaNode[E: str]:
    """JSON Schema keyword dispatch.

    - x-* extensions -> data
    - Known keywords -> looked up in table
    - Unknown keywords -> (fallback, _NO_BHV)
    """

    opaque = False

    def __init__(self, kind: E) -> None:
        self._kind = kind
        self._keywords: dict[str, tuple[Node[Any], Behavior]] = {}
        self._fallback: Node[Any] | None = None

    @property
    def kind(self) -> E:
        return self._kind

    def configure(
        self,
        keywords: dict[str, tuple[Node[Any], Behavior]],
        fallback: Node[Any],
    ) -> None:
        self._keywords = keywords
        self._fallback = fallback

    def child(self, prop: str) -> tuple[Node[Any], Behavior]:
        if prop.startswith("x-"):
            return (data, _NO_BHV)
        assert self._fallback is not None, f"{self._kind} not configured"
        return self._keywords.get(prop, (self._fallback, _NO_BHV))

    def __repr__(self) -> str:
        return str(self._kind)


type DraftKeys[E: str] = E | SchemaKind | Literal["data"]
