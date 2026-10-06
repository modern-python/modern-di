import dataclasses
import functools
import inspect
import sys
import typing

import pytest

from modern_di import Container, Group, Scope, exceptions, providers, types
from modern_di.types_parser import SignatureItem, _signature, parse_creator


class GenericClass(typing.Generic[types.T]): ...


if typing.TYPE_CHECKING:
    from typing import Protocol


@pytest.mark.parametrize(
    ("type_", "result"),
    [
        (int, SignatureItem(arg_type=int)),
        (typing.Annotated[int, None], SignatureItem(arg_type=int)),
        (list[int], SignatureItem(unresolvable_generic=list[int])),
        (dict[str, typing.Any], SignatureItem(unresolvable_generic=dict[str, typing.Any])),
        (typing.Optional[str], SignatureItem(arg_type=str, is_nullable=True)),  # noqa: UP045
        (str | None, SignatureItem(arg_type=str, is_nullable=True)),
        (str | int, SignatureItem(member_types=[str, int])),
        (typing.Union[str | int], SignatureItem(member_types=[str, int])),  # noqa: UP007
        (list[str] | None, SignatureItem(arg_type=list, is_nullable=True)),
        (GenericClass[str], SignatureItem(unresolvable_generic=GenericClass[str])),
        (GenericClass[str] | None, SignatureItem(arg_type=GenericClass, is_nullable=True)),
        (typing.Generic, SignatureItem(unresolvable_generic=typing.Generic)),
        # `None` is the degenerate nullable: a union with zero non-None members.
        (type(None), SignatureItem(is_nullable=True)),
    ],
)
def test_signature_item_parser(type_: type, result: SignatureItem) -> None:
    assert SignatureItem.from_type(type_) == result


def test_union_member_degrades_to_bare_origin() -> None:
    """INVARIANT: inside a union, each member degrades to its bare origin type; the element type is not enforced.

    `list[str] | None` and `GenericClass[str] | None` both resolve to `arg_type=list` and
    `arg_type=GenericClass` — the element type is dropped, not enforced. `int | list[str]` can match a
    provider registered for plain `list` regardless of what it holds. This is intentional and not a
    wiring guarantee: the asymmetry with the bare-generic case (`list[str]` alone raises
    `UnsupportedCreatorParameterError` at declaration — see
    `test_parameterized_generic_param_without_default_raises_at_declaration`) is deliberate, not a bug
    to reconcile by making one side match the other.
    """
    assert SignatureItem.from_type(list[str] | None) == SignatureItem(  # ty: ignore[invalid-argument-type]
        arg_type=list, is_nullable=True
    )
    assert SignatureItem.from_type(GenericClass[str] | None) == SignatureItem(  # ty: ignore[invalid-argument-type]
        arg_type=GenericClass, is_nullable=True
    )


@pytest.mark.parametrize("default", [None, 3, "x"])
def test_nonetype_threads_its_default(default: object) -> None:
    """A `None`-annotated parameter keeps its default, like every other annotation.

    Exercised through `from_type` rather than a real creator: only `None` is assignable
    to a `None`-annotated parameter, so a non-None default cannot be spelled in a signature.
    """
    assert SignatureItem.from_type(type(None), default=default) == SignatureItem(default=default, is_nullable=True)


def nonetype_func(hook: None = None) -> None: ...


def test_nonetype_params_keep_defaults_through_parse_creator() -> None:
    params = parse_creator(nonetype_func).params
    assert params["hook"] == SignatureItem(default=None, is_nullable=True)


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
                # `-> None` is nullable; only `.arg_type` (None) is read, to derive bound_type.
                SignatureItem(is_nullable=True),
                {
                    "arg1": SignatureItem(arg_type=int),
                    "arg2": SignatureItem(arg_type=str, is_nullable=True, default=None),
                },
            ),
        ),
        (
            args_kwargs_func,
            (
                SignatureItem(is_nullable=True),
                {},
            ),
        ),
        (
            func_with_str_annotations,
            (
                SignatureItem(is_nullable=True),
                {
                    "arg1": SignatureItem(arg_type=str),
                    "arg2": SignatureItem(unresolvable_generic=tuple[int, ...], default=()),
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
                    # kw_only=True dataclass -> both fields are keyword-only.
                    "arg1": SignatureItem(arg_type=str, is_keyword_only=True),
                    "arg2": SignatureItem(arg_type=int, is_keyword_only=True),
                },
            ),
        ),
        (
            DataClassInitFalse,
            (
                SignatureItem(arg_type=DataClassInitFalse),
                {
                    "arg1": SignatureItem(arg_type=str, is_keyword_only=True),
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
    parsed = parse_creator(creator)
    assert (parsed.return_type, parsed.params) == result


@pytest.mark.parametrize(
    ("creator", "result"),
    [
        (func_with_wrong_annotations, (SignatureItem(), {"arg1": SignatureItem(), "arg2": SignatureItem()})),
        (
            ClassWithWrongAnnotations,
            (SignatureItem(arg_type=ClassWithWrongAnnotations), {"arg1": SignatureItem(), "arg2": SignatureItem()}),
        ),
    ],
)
def test_parse_creator_with_unresolvable_annotations_warns(
    creator: type, result: tuple[SignatureItem | None, dict[str, SignatureItem]]
) -> None:
    with pytest.warns(UserWarning, match="Failed to resolve type hints"):
        parsed = parse_creator(creator)
    assert (parsed.return_type, parsed.params) == result


def test_parse_creator_str_generic_annotation_without_default_raises() -> None:
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match="arg1"):
        providers.Factory(creator=func_with_str_generic_annotation)


def _partial_target(x: int, y: int) -> int:
    return x + y


def test_get_type_hints_typeerror_is_warn_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # B-2: a TypeError from get_type_hints (e.g. functools.partial on <=3.13, or any object
    # it rejects) must be warn-skipped, not crash. Injected directly because the real trigger
    # is version-dependent: 3.14 made functools.partial introspectable (returns {} instead of
    # raising), so a real partial no longer exercises this branch on every interpreter.
    def _raise_type_error(*_args: object, **_kwargs: object) -> dict[str, object]:
        msg = "synthetic: not a module, class, method, or function"
        raise TypeError(msg)

    monkeypatch.setattr(typing, "get_type_hints", _raise_type_error)
    with pytest.warns(UserWarning, match="skip_creator_parsing"):
        provider = providers.Factory(creator=_partial_target, bound_type=int)
    assert provider is not None


def test_partial_creator_does_not_crash() -> None:
    # B-2 motivating case: declaring a Factory from a functools.partial must not crash on any
    # supported Python. On <=3.13 get_type_hints raises TypeError (warn-skipped); on 3.14+ it
    # returns {} (parsed cleanly). Either way construction succeeds.
    partial = functools.partial(_partial_target, y=1)
    if sys.version_info >= (3, 14):
        provider = providers.Factory(creator=partial, bound_type=int)
    else:
        with pytest.warns(UserWarning, match="skip_creator_parsing"):
            provider = providers.Factory(creator=partial, bound_type=int)
    assert provider.bound_type is int


class _GenericDep: ...


def _generic_param_creator(x: list[_GenericDep]) -> str:
    return str(x)


def test_parameterized_generic_param_without_default_raises_at_declaration() -> None:
    assert _generic_param_creator([]) == "[]"
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match=r"list\[.*_GenericDep\]") as exc_info:
        providers.Factory(creator=_generic_param_creator)
    assert "skip_creator_parsing" not in str(exc_info.value)


def _bare_generic_param_creator(x: typing.Generic) -> str:  # ty: ignore[invalid-type-form]
    return str(x)


def test_bare_generic_param_without_default_raises_at_declaration() -> None:
    assert _bare_generic_param_creator(1) == "1"
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match=r"typing\.Generic"):
        providers.Factory(creator=_bare_generic_param_creator)


def test_parameterized_generic_param_supplied_via_kwargs_is_allowed() -> None:
    sentinel = [_GenericDep()]
    provider = providers.Factory(creator=_generic_param_creator, kwargs={"x": sentinel})
    container = Container(scope=Scope.APP)
    container.add_providers(provider)
    assert container.resolve(str) == str(sentinel)


def _generic_param_with_default(x: tuple[str, ...] = ()) -> str:
    return str(x)


def test_parameterized_generic_param_with_default_is_allowed() -> None:
    assert _generic_param_with_default(("a",)) == str(("a",))
    provider = providers.Factory(creator=_generic_param_with_default)
    container = Container(scope=Scope.APP)
    container.add_providers(provider)
    assert container.resolve(str) == str(())


def _pos_only_creator(x: int, /, y: int) -> int:
    return x + y


def test_positional_only_param_raises_at_declaration() -> None:
    assert _pos_only_creator(1, y=2) == _pos_only_creator(2, y=1)
    with pytest.raises(exceptions.UnsupportedCreatorParameterError, match="positional-only") as exc_info:
        providers.Factory(creator=_pos_only_creator)
    # kwargs cannot help: the creator is always invoked creator(**kwargs)
    assert "kwargs" not in str(exc_info.value)
    assert "skip_creator_parsing" not in str(exc_info.value)


def _pos_only_with_default(x: int = 0, /, y: int = 1) -> int:
    return x + y


def test_positional_only_param_with_default_is_skipped() -> None:
    assert _pos_only_with_default(2) == _pos_only_with_default(1, 2)
    parsed = parse_creator(_pos_only_with_default)
    assert (parsed.return_type, parsed.params) == (
        SignatureItem(arg_type=int),
        {"y": SignatureItem(arg_type=int, default=1)},
    )
    # the dropped positional-only `x` is recorded so the compiled fast path keeps **kwargs
    assert parsed.has_positional_only_gap is True


def _mixed_kind_creator(pos_or_kw: int, *, kw_only: int) -> int:
    return pos_or_kw + kw_only


def test_keyword_only_signal_recorded() -> None:
    # A keyword-only parameter records is_keyword_only=True; a positional-or-keyword one records
    # False. This is the only param-kind signal the compiled positional fast path consults.
    params = parse_creator(_mixed_kind_creator).params
    assert params["pos_or_kw"].is_keyword_only is False
    assert params["kw_only"].is_keyword_only is True


class _Dep: ...


class _OtherDep: ...


class _NamedTupleCreator(typing.NamedTuple):
    dep: _Dep
    label: str = "x"


class _NamedTupleForwardRef(typing.NamedTuple):
    dep: "_LateDep"


class _LateDep(_Dep): ...


class _NewOnlyCreator:
    def __new__(cls, dep: _Dep) -> typing.Self:
        instance = super().__new__(cls)
        instance.dep = dep  # ty: ignore[unresolved-attribute]
        return instance


class _NewOnlySubclass(_NewOnlyCreator): ...


@pytest.mark.parametrize(
    ("creator", "dep_type"),
    [
        (_NamedTupleCreator, _Dep),
        (_NamedTupleForwardRef, _LateDep),
        (_NewOnlyCreator, _Dep),
        (_NewOnlySubclass, _Dep),
    ],
)
def test_hints_come_from_the_callable_the_signature_reads(creator: type, dep_type: type) -> None:
    assert parse_creator(creator).params["dep"] == SignatureItem(arg_type=dep_type)

    class Dependencies(Group):
        dep = providers.Factory(dep_type)
        target = providers.Factory(creator)

    container = Container(groups=[Dependencies])
    assert isinstance(container.resolve(creator).dep, dep_type)  # ty: ignore[unresolved-attribute]


_UserId = typing.NewType("_UserId", int)
_UserIdAlias = typing.TypeAliasType("_UserIdAlias", int) if sys.version_info >= (3, 12) else None
_NAMED_TYPE_FORMS = [
    pytest.param(_UserId, id="NewType"),
    pytest.param(
        _UserIdAlias,
        id="TypeAliasType",
        marks=pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 type aliases need Python 3.12"),
    ),
]


def _greeter_of(form: object) -> typing.Callable[..., str]:
    def greet(user_id) -> str:  # noqa: ANN001
        return f"u{user_id}"

    greet.__annotations__ = {"user_id": form, "return": str}
    return greet


@pytest.mark.parametrize("form", _NAMED_TYPE_FORMS)
def test_named_type_form_parameter_matches_provider_bound_to_it(form: type) -> None:
    assert SignatureItem.from_type(form) == SignatureItem(arg_type=form)

    class Dependencies(Group):
        user_id = providers.Factory(lambda: 7, bound_type=form)
        greeting = providers.Factory(_greeter_of(form))

    assert Container(groups=[Dependencies]).resolve(str) == "u7"


@pytest.mark.parametrize("form", _NAMED_TYPE_FORMS)
def test_named_type_form_return_annotation_is_the_bound_type(form: type) -> None:
    def make() -> int: ...  # ty: ignore[empty-body]

    make.__annotations__ = {"return": form}
    assert providers.Factory(make).bound_type is form


@pytest.mark.parametrize("form", _NAMED_TYPE_FORMS)
def test_unregistered_named_type_form_names_the_annotation(form: type) -> None:
    class Dependencies(Group):
        greeting = providers.Factory(_greeter_of(form))

    with pytest.raises(exceptions.ArgumentResolutionError) as exc_info:
        Container(groups=[Dependencies]).resolve(str)
    assert "no usable type annotation" not in str(exc_info.value)
    assert "_UserId" in str(exc_info.value)


def _make_dep_or_other() -> _Dep | _OtherDep: ...  # ty: ignore[empty-body]
def _make_optional_dep() -> _Dep | None: ...


def test_union_return_type_without_bound_type_warns() -> None:
    with pytest.warns(UserWarning, match="bound_type") as record:
        provider = providers.Factory(_make_dep_or_other)
    assert provider.bound_type is None
    assert "_Dep | _OtherDep" in str(record[0].message)


@pytest.mark.parametrize(
    ("creator", "bound_type"),
    [(_make_dep_or_other, _Dep), (_make_dep_or_other, None), (_make_optional_dep, types.UNSET)],
)
def test_union_return_type_is_silent_when_bound_type_is_known(
    creator: typing.Callable[..., typing.Any], bound_type: type | None
) -> None:
    providers.Factory(creator, bound_type=bound_type)


class _PlainInit:
    def __init__(self, dep: _Dep, label: str = "x") -> None:
        """Never called: these classes exist for their signatures."""


class _InheritsInit(_PlainInit):
    """Inherits its ``__init__``."""


@dataclasses.dataclass(slots=True)
class _SlotsDataclass:
    dep: _Dep


class _GeneratedInit:
    __init__ = eval("lambda self, dep: None")  # noqa: S307  # an attrs-style generated __init__


class _StarArgsInit:
    def __init__(*args: object, dep: _Dep) -> None:
        """Never called."""


class _NoSelfInit:
    def __init__() -> None:
        """Never called."""


class _WrappedInit:
    @functools.wraps(_PlainInit.__init__)
    def __init__(self, *args: object, **kwargs: object) -> None:
        """Never called."""


class _SignatureOverride:
    __signature__ = inspect.Signature([inspect.Parameter("dep", inspect.Parameter.KEYWORD_ONLY, annotation=_Dep)])

    def __init__(self, **kwargs: object) -> None:
        """Never called."""


class _InitOverNew(_NewOnlyCreator):
    def __init__(self, dep: _Dep, label: str) -> None:
        """Never called."""


class _InitBesideNew:
    def __new__(cls, *args: object, **kwargs: object) -> typing.Self:  # noqa: ARG004
        return super().__new__(cls)

    def __init__(self, dep: _Dep) -> None:
        """Never called."""


class _CallingMeta(type):
    def __call__(cls, other: _OtherDep) -> object:
        return other


class _MetaCall(metaclass=_CallingMeta):
    def __init__(self, dep: _Dep) -> None:
        """Never called."""


class _PlainMeta(type):
    """A metaclass with no ``__call__``."""


class _MetaNoCall(metaclass=_PlainMeta):
    def __init__(self, dep: _Dep) -> None:
        """Never called."""


class _GenericInit(typing.Generic[types.T]):
    def __init__(self, dep: _Dep) -> None:
        """Never called."""


class _InitError(Exception):
    def __init__(self, dep: _Dep) -> None:
        """Never called."""


class _StaticInit:
    __init__ = staticmethod(lambda dep: None)  # noqa: ARG005


class _NoInit:
    """Defines neither ``__new__`` nor ``__init__``."""


@pytest.mark.parametrize(
    "creator",
    [
        _PlainInit,
        _InheritsInit,
        SomeDataClass,
        _SlotsDataclass,
        _GeneratedInit,
        _StarArgsInit,
        _NoSelfInit,
        _WrappedInit,
        _SignatureOverride,
        _NamedTupleCreator,
        _NewOnlyCreator,
        _NewOnlySubclass,
        _InitOverNew,
        _InitBesideNew,
        _MetaCall,
        _MetaNoCall,
        _GenericInit,
        _InitError,
        _StaticInit,
        _NoInit,
        _UserId,
        _greeter_of(int),
        functools.partial(_PlainInit, label="y"),
    ],
)
def test_class_signature_matches_inspect_signature(creator: typing.Callable[..., object]) -> None:
    """INVARIANT: `_signature` reads the same signature `inspect.signature` does, error included."""
    try:
        expected: object = inspect.signature(creator)
    except ValueError as exc:
        expected = (ValueError, str(exc))
    try:
        actual: object = _signature(creator)
    except ValueError as exc:
        actual = (ValueError, str(exc))
    assert actual == expected
