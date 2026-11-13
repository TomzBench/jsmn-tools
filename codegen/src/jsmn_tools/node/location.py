from __future__ import annotations

from typing import Any


class Location(tuple):
    """Document location as a tuple of path segments.

    Convertible to/from JSON Pointer (RFC 6901).
    """

    def to_pointer(self) -> str:
        if not self:
            return ""
        return "/" + "/".join(
            s.replace("~", "~0").replace("/", "~1") for s in self
        )

    @classmethod
    def from_pointer(cls, pointer: str) -> Location:
        if not pointer or pointer == "/":
            return cls()
        segments = pointer.lstrip("/").split("/")
        return cls(s.replace("~1", "/").replace("~0", "~") for s in segments)

    @classmethod
    def from_segments(cls, *segments: str) -> Location:
        return cls(segments)

    def push(self, key: str) -> Location:
        return Location((*self, key))

    def resolve(self, doc: Any) -> Any:
        """The value at this location in *doc*; LookupError if there is none."""
        node = doc
        for key in self:
            try:
                node = node[int(key)] if isinstance(node, list) else node[key]
            except (LookupError, TypeError, ValueError):
                raise LookupError(self.to_pointer()) from None
        return node

    def get(self, doc: Any, default: Any = None) -> Any:
        """The value at this location in *doc*, or *default* if there is none.

        ``None`` is a legal value in a document; pass a sentinel as *default*
        to tell a null from a miss.
        """
        try:
            return self.resolve(doc)
        except LookupError:
            return default

    def exists(self, doc: Any) -> bool:
        """Whether *doc* has a value at this location."""
        return self.get(doc, _MISSING) is not _MISSING


_MISSING: Any = object()


ROOT = Location()
