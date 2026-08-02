from typing import Literal

PathExistsPolicy = Literal["allow_missing", "must_exist"]
ViewTarget = Literal["pydantic", "dataclass", "dict"]

__all__ = ["PathExistsPolicy", "ViewTarget"]
