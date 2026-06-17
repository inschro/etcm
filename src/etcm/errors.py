from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    source_path: Path | None = None
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    selector: str | None = None
    graph_path: str | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.details is not None:
            object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


class ETCMError(Exception):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class ETCMNotImplementedError(NotImplementedError):
    pass
