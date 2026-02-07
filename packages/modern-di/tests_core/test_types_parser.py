import dataclasses
import typing

import pytest
from modern_di import types
from modern_di.types_parser import SignatureItem, parse_creator


class GenericClass(typing.Generic[types.T]): ...


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


def simple_func(arg1: int, arg2: str | None = None) -> int: ...  # type: ignore[empty-body]
def none_func(arg1: typing.Annotated[int, None], arg2: str | None = None) -> None: ...
def args_kwargs_func(*args: int, **kwargs: str) -> None: ...
def func_with_str_annotations(arg1: "list[int]", arg2: "str") -> None: ...
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


class ClassWithStringAnnotations:
    def __init__(self, arg1: "str", arg2: "int") -> None: ...


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
    ],
)
def test_parse_creator(creator: type, result: tuple[SignatureItem | None, dict[str, SignatureItem]]) -> None:
    assert parse_creator(creator) == result


def func_with_wrong_annotations(arg1: "WrongType", arg2: "str") -> None: ...  # type: ignore[name-defined]  # noqa: F821


class ClassWithWrongAnnotations:
    def __init__(self, arg1: "WrongType", arg2: "int") -> None: ...  # type: ignore[name-defined]  # noqa: F821


@pytest.mark.parametrize(
    "creator",
    [func_with_wrong_annotations, ClassWithWrongAnnotations],
)
def test_parse_creator_wrong_annotations(creator: type) -> None:
    with pytest.raises(NameError, match="name 'WrongType' is not defined"):
        assert parse_creator(creator)
