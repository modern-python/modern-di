import dataclasses
import functools
import typing

import pytest

from modern_di import Container, Scope, exceptions, providers, types
from modern_di.types_parser import SignatureItem, parse_creator


class GenericClass(typing.Generic[types.T]): ...


if typing.TYPE_CHECKING:
    from typing import Protocol


@pytest.mark.parametrize(
    ("type_", "result"),
    [
        (int, SignatureItem(arg_type=int)),
        (typing.Annotated[int, None], SignatureItem(arg_type=int)),
        (list[int], SignatureItem(raw_annotation=list[int])),
        (dict[str, typing.Any], SignatureItem(raw_annotation=dict[str, typing.Any])),
        (typing.Optional[str], SignatureItem(arg_type=str, is_nullable=True)),  # noqa: UP045
        (str | None, SignatureItem(arg_type=str, is_nullable=True)),
        (str | int, SignatureItem(args=[str, int])),
        (typing.Union[str | int], SignatureItem(args=[str, int])),  # noqa: UP007
        (list[str] | None, SignatureItem(arg_type=list, is_nullable=True)),
        (GenericClass[str], SignatureItem(raw_annotation=GenericClass[str])),
        (GenericClass[str] | None, SignatureItem(arg_type=GenericClass, is_nullable=True)),
    ],
)
def test_signature_item_parser(type_: type, result: SignatureItem) -> None:
    assert SignatureItem.from_type(type_) == result


def simple_func(arg1: int, arg2: str | None = None) -> int: ...  # ty: ignore[empty-body]
def none_func(arg1: typing.Annotated[int, None], arg2: str | None = None) -> None: ...
def args_kwargs_func(*args: int, **kwargs: str) -> None: ...
def func_with_str_annotations(arg1: "str", arg2: "tuple[int, ...]" = ()) -> None: ...
def func_with_str_generic_annotation(arg1: "list[int]", arg2: "str") -> None: ...
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
                    "arg1": SignatureItem(arg_type=str),
                    "arg2": SignatureItem(raw_annotation=tuple[int, ...], default=()),
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


def test_parse_creator_str_generic_annotation_without_default_raises() -> None:
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match="arg1"):
        providers.Factory(creator=func_with_str_generic_annotation)


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


class _GenericDep: ...


def _generic_param_creator(x: list[_GenericDep]) -> str:
    return str(x)


def test_parameterized_generic_param_without_default_raises_at_declaration() -> None:
    assert _generic_param_creator([]) == "[]"
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match=r"list\[.*_GenericDep\]"):
        providers.Factory(creator=_generic_param_creator)


def test_parameterized_generic_param_supplied_via_kwargs_is_allowed() -> None:
    sentinel = [_GenericDep()]
    provider = providers.Factory(creator=_generic_param_creator, kwargs={"x": sentinel})
    container = Container(scope=Scope.APP)
    container.providers_registry.register(str, provider)
    assert container.resolve(str) == str(sentinel)


def _generic_param_with_default(x: tuple[str, ...] = ()) -> str:
    return str(x)


def test_parameterized_generic_param_with_default_is_allowed() -> None:
    assert _generic_param_with_default(("a",)) == str(("a",))
    provider = providers.Factory(creator=_generic_param_with_default)
    assert provider is not None


def _pos_only_creator(x: int, /, y: int) -> int:
    return x + y


def test_positional_only_param_raises_at_declaration() -> None:
    assert _pos_only_creator(1, y=2) == _pos_only_creator(2, y=1)
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match="positional-only") as exc_info:
        providers.Factory(creator=_pos_only_creator)
    # kwargs cannot help: the creator is always invoked creator(**kwargs)
    assert "kwargs" not in str(exc_info.value)


def _pos_only_with_default(x: int = 0, /, y: int = 1) -> int:
    return x + y


def test_positional_only_param_with_default_is_skipped() -> None:
    assert _pos_only_with_default(2) == _pos_only_with_default(1, 2)
    assert parse_creator(_pos_only_with_default) == (
        SignatureItem(arg_type=int),
        {"y": SignatureItem(arg_type=int, default=1)},
    )
