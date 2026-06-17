from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from etcm.errors import ETCMNotImplementedError

PathExistsPolicy = Literal["allow_missing", "must_exist"]

_STAGE2_MESSAGE = "ETCM resolver behavior is not implemented in Stage 2."


@dataclass(frozen=True)
class Resolver:
    path_exists: PathExistsPolicy = "allow_missing"

    def __post_init__(self) -> None:
        if self.path_exists not in ("allow_missing", "must_exist"):
            raise ValueError("path_exists must be 'allow_missing' or 'must_exist'")

    def load(self, selector: str, *, as_: str = "pydantic") -> object:
        raise ETCMNotImplementedError(_STAGE2_MESSAGE)

    def resolve(self, selector: str) -> object:
        raise ETCMNotImplementedError(_STAGE2_MESSAGE)

    def validate(self, selector: str) -> None:
        raise ETCMNotImplementedError(_STAGE2_MESSAGE)


def load(selector: str, *, as_: str = "pydantic") -> object:
    return Resolver().load(selector, as_=as_)


def resolve(selector: str) -> object:
    return Resolver().resolve(selector)


def validate(selector: str) -> None:
    return Resolver().validate(selector)
