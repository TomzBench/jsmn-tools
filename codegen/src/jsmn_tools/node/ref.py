from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ref:
    raw: str

    @property
    def is_local(self) -> bool:
        return self.raw.startswith("#")

    @property
    def is_relative(self) -> bool:
        return self.raw.startswith("./")

    @property
    def fragment(self) -> str | None:
        """The part after ``#``; None when the ref has no fragment."""
        _, sep, fragment = self.raw.partition("#")
        return fragment if sep else None
