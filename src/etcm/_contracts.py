from collections.abc import Mapping, Sequence
from typing import Any, Literal

type OverrideInput = Mapping[str, Any] | Sequence[str]
PathExistsPolicy = Literal["allow_missing", "must_exist"]
ViewTarget = Literal["pydantic", "dataclass", "dict"]

__all__ = ["OverrideInput", "PathExistsPolicy", "ViewTarget"]
