import dataclasses
import functools
import typing

import pytest

from modern_di import providers, types
from modern_di.types_parser import SignatureItem, parse_creator


class GenericClass(typing.Generic[types.T]): ...


if typing.TYPE_CHECKING:
    from typing import Protocol


@pytest.mark.parametrize(
    ("type_", "result"),
    [
        (int, SignatureItem(arg_type=int)),
        (typing.Annotated[int, None], SignatureItem(arg_type=int)),
        (list[int], SignatureItem(arg_type=list, args=[int])),
        (dict[str, typing.Any], SignatureItem(arg_type=dict, args=[str, typing.Any])),
        (typing.Optional[str], SignatureItem(arg_type=str, is_nullable=True)),  # noqa: UP045
        (str | None, SignatureItem(arg_type=str, is_nullable=True)),
        (str | int, SignatureItem(args=[str, int])),
        (typing.Union[str | int], SignatureItem(args=[str, int])),  # noqa: UP007
        (list[str] | None, SignatureItem(arg_type=list, is_nullable=True)),
        (GenericClass[str], SignatureItem(arg_type=GenericClass, args=[str])),
        (GenericClass[str] | None, SignatureItem(arg_type=GenericClass, is_nullable=True)),
    ],
)
def test_signature_item_parser(type_: type, result: SignatureItem) -> None:
    assert SignatureItem.from_type(type_) == result


def simple_func(arg1: int, arg2: str | None = None) -> int: ...  # ty: ignore[empty-body]
def none_func(arg1: typing.Annotated[int, None], arg2: str | None = None) -> None: ...
def args_kwargs_func(*args: int, **kwargs: str) -> None: ...
def func_with_str_annotations(arg1: "list[int]", arg2: "str") -> None: ...
async def async_func(arg1: int = 1, arg2="str") -> int: ...  # ty: ignore[empty-body]  # noqa: ANN001


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SomeDataClass:
    arg1: str
    arg2: int


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DataClassInitFalse:
    arg1: str
    arg2: int = dataclasses.field(init=False)


class SomeRegularClass:
    def __init__(self, arg1: str, arg2: int) -> None: ...


class ClassWithStringAnnotations:
    def __init__(self, arg1: "str", arg2: "int") -> None: ...


def func_with_wrong_annotations(arg1: "Protocol", arg2: "str") -> None: ...  # ty: ignore[invalid-type-form]


class ClassWithWrongAnnotations:
    def __init__(self, arg1: "WrongType", arg2: "int") -> None: ...  # ty: ignore[unresolved-reference]  # noqa: F821


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
            func_with_str_annotations,
            (
                SignatureItem(),
                {
                    "arg1": SignatureItem(arg_type=list, args=[int]),
                    "arg2": SignatureItem(arg_type=str),
                },
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
        (
            ClassWithStringAnnotations,
            (
                SignatureItem(arg_type=ClassWithStringAnnotations),
                {
                    "arg1": SignatureItem(arg_type=str),
                    "arg2": SignatureItem(arg_type=int),
                },
            ),
        ),
        (int, (SignatureItem(arg_type=int), {})),
        (func_with_wrong_annotations, (SignatureItem(), {"arg1": SignatureItem(), "arg2": SignatureItem()})),
        (
            ClassWithWrongAnnotations,
            (SignatureItem(arg_type=ClassWithWrongAnnotations), {"arg1": SignatureItem(), "arg2": SignatureItem()}),
        ),
    ],
)
def test_parse_creator(creator: type, result: tuple[SignatureItem | None, dict[str, SignatureItem]]) -> None:
    assert parse_creator(creator) == result


def _partial_target(x: int, y: int) -> int:
    return x + y


def test_partial_creator_warns_and_skips_instead_of_crashing() -> None:
    partial = functools.partial(_partial_target, y=1)
    assert partial(x=2) == _partial_target(x=2, y=1)  # exercise _partial_target body for coverage
    with pytest.warns(UserWarning, match="skip_creator_parsing"):
        provider = providers.Factory(
            creator=partial,
            bound_type=int,
        )
    assert provider is not None
