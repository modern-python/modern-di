import dataclasses
import typing

import pytest
from modern_di.types_parser import SignatureItem, parse_creator


@pytest.mark.parametrize(
    ("type_", "result"),
    [
        (int, SignatureItem(arg_type=int)),
        (list[int], SignatureItem(arg_type=list, args=[int])),
        (dict[str, typing.Any], SignatureItem(arg_type=dict, args=[str, typing.Any])),
        (typing.Optional[str], SignatureItem(arg_type=str, is_nullable=True)),  # noqa: UP045
        (str | None, SignatureItem(arg_type=str, is_nullable=True)),
        (str | int, SignatureItem(args=[str, int])),
        (list[str] | None, SignatureItem(arg_type=list, is_nullable=True)),
    ],
)
def test_signature_item_parser(type_: type, result: SignatureItem) -> None:
    assert SignatureItem.from_type(type_) == result


def simple_func(arg1: int, arg2: str | None = None) -> int: ...  # type: ignore[empty-body]
def none_func(arg1: int, arg2: str | None = None) -> None: ...
def args_kwargs_func(*args: int, **kwargs: str) -> None: ...
async def async_func(arg1: int = 1, arg2="str") -> int: ...  # type: ignore[no-untyped-def,empty-body]  # noqa: ANN001


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SomeDataClass:
    arg1: str
    arg2: int


@dataclasses.dataclass(kw_only=True, slots=True)
class DataClassInitFalse:
    arg1: str
    arg2: int = dataclasses.field(init=False)


class SomeRegularClass:
    def __init__(self, arg1: str, arg2: int) -> None: ...


@pytest.mark.parametrize(
    ("creator", "result"),
    [
        (
            simple_func,
            (
                SignatureItem(arg_type=int),
                {
                    "arg1": SignatureItem(arg_type=int),
                    "arg2": SignatureItem(arg_type=str, is_nullable=True, default=None),
                },
            ),
        ),
        (
            none_func,
            (
                SignatureItem(),
                {
                    "arg1": SignatureItem(arg_type=int),
                    "arg2": SignatureItem(arg_type=str, is_nullable=True, default=None),
                },
            ),
        ),
        (
            args_kwargs_func,
            (
                SignatureItem(),
                {},
            ),
        ),
        (
            async_func,
            (
                SignatureItem(arg_type=int),
                {
                    "arg1": SignatureItem(arg_type=int, default=1),
                    "arg2": SignatureItem(default="str"),
                },
            ),
        ),
        (
            SomeDataClass,
            (
                SignatureItem(arg_type=SomeDataClass),
                {
                    "arg1": SignatureItem(arg_type=str),
                    "arg2": SignatureItem(arg_type=int),
                },
            ),
        ),
        (
            DataClassInitFalse,
            (
                SignatureItem(arg_type=DataClassInitFalse),
                {
                    "arg1": SignatureItem(arg_type=str),
                },
            ),
        ),
        (
            SomeRegularClass,
            (
                SignatureItem(arg_type=SomeRegularClass),
                {
                    "arg1": SignatureItem(arg_type=str),
                    "arg2": SignatureItem(arg_type=int),
                },
            ),
        ),
        (int, (SignatureItem(arg_type=int), {})),
    ],
)
def test_parse_creator(creator: type, result: tuple[SignatureItem | None, dict[str, SignatureItem]]) -> None:
    assert parse_creator(creator) == result
