from collections.abc import Callable

import pytest

from etcm import Resolver, load, resolve, validate
from etcm.errors import ETCMNotImplementedError


def test_resolver_accepts_path_policy() -> None:
    assert Resolver().path_exists == "allow_missing"
    assert Resolver(path_exists="must_exist").path_exists == "must_exist"


def test_resolver_rejects_unknown_path_policy() -> None:
    with pytest.raises(ValueError, match="path_exists"):
        Resolver(path_exists="sometimes")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "call",
    [
        lambda: load("configs/train.etcm#smoke"),
        lambda: resolve("configs/train.etcm#smoke"),
        lambda: validate("configs/train.etcm#smoke"),
        lambda: Resolver().load("configs/train.etcm#smoke"),
        lambda: Resolver().resolve("configs/train.etcm#smoke"),
        lambda: Resolver().validate("configs/train.etcm#smoke"),
    ],
)
def test_public_api_placeholders_are_explicit(call: Callable[[], object]) -> None:
    with pytest.raises(ETCMNotImplementedError, match="Stage 2"):
        call()
