import dataclasses
import inspect
import sys
import types
import typing
import warnings

from modern_di import exceptions
from modern_di.types import UNSET


_NAMED_TYPE_FORMS = (typing.NewType,) if sys.version_info < (3, 12) else (typing.NewType, typing.TypeAliasType)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SignatureItem:
    arg_type: type | None = None
    member_types: list[type] = dataclasses.field(default_factory=list)
    is_nullable: bool = False
    default: object = UNSET
    unresolvable_generic: object = None
    is_keyword_only: bool = False

    @classmethod
    def from_type(cls, type_: type, default: object = UNSET) -> "SignatureItem":
        if type_ is types.NoneType:
            # The degenerate nullable: the union branch below would take it for a plain type and
            # try to resolve `NoneType` from the registry.
            return cls(default=default, is_nullable=True)
        if type(type_) is type and type_ is not typing.Generic:  # `get_origin(Generic)` is `Generic`
            return cls(arg_type=type_, default=default)

        origin = typing.get_origin(type_)
        if origin is typing.Annotated:
            type_ = typing.get_args(type_)[0]
            origin = typing.get_origin(type_)

        result: dict[str, typing.Any] = {"default": default}

        if isinstance(type_, types.UnionType) or origin is typing.Union:
            # A parameterized generic member degrades to its origin (list[str] -> list); see
            # test_union_member_degrades_to_bare_origin.
            union_members = [typing.get_origin(x) or x for x in typing.get_args(type_)]
            non_none_members = [member for member in union_members if member is not types.NoneType]
            if len(non_none_members) != len(union_members):
                result["is_nullable"] = True

            if len(non_none_members) > 1:
                result["member_types"] = non_none_members
            else:
                result["arg_type"] = non_none_members[0]

        elif origin is not None:
            result["unresolvable_generic"] = type_

        elif isinstance(type_, (type, _NAMED_TYPE_FORMS)):
            result["arg_type"] = type_

        return cls(**result)


def _parse_parameter(
    creator: typing.Callable[..., typing.Any],
    param_name: str,
    param: inspect.Parameter,
    type_hints: dict[str, typing.Any],
) -> SignatureItem | None:
    if param.kind is inspect.Parameter.POSITIONAL_ONLY:
        if param.default is not param.empty:
            # None is a signal, not "no item": parse_creator reads it as a positional-only gap.
            return None
        raise exceptions.UnsupportedCreatorParameterError(
            creator=creator,
            parameter_name=param_name,
            reason="positional-only parameters cannot be passed by keyword; give the parameter a default",
        )

    default = UNSET
    if param.default is not param.empty:
        default = param.default

    if param_name in type_hints:
        item = SignatureItem.from_type(type_hints[param_name], default=default)
    else:
        item = SignatureItem(default=default)
    if param.kind is inspect.Parameter.KEYWORD_ONLY:
        return dataclasses.replace(item, is_keyword_only=True)
    return item


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ParsedCreator:
    """A creator's signature as the wiring reads it.

    ``has_positional_only_gap`` is True when a positional-only-with-default parameter was dropped
    from ``params``, so the map is no longer a faithful positional prefix of the signature.
    ``accepts_any_kwargs`` is True when the creator takes ``**kwargs`` or its signature cannot be
    read, so no ``kwargs={...}`` key can be called unknown.
    """

    return_type: SignatureItem
    params: dict[str, SignatureItem]
    has_positional_only_gap: bool
    accepts_any_kwargs: bool


def _class_type_hints(creator: type) -> dict[str, typing.Any]:
    """Return the hints of the ``__new__`` or ``__init__`` that ``inspect.signature`` reads for a class."""
    for base in creator.__mro__:
        for name in ("__new__", "__init__"):
            if name in base.__dict__ and inspect.isfunction(method := getattr(base, name)):
                module = sys.modules.get(base.__module__)
                return typing.get_type_hints(method, localns=vars(module) if module else None)
    return typing.get_type_hints(creator.__init__)


def _signature(creator: typing.Callable[..., typing.Any]) -> inspect.Signature:
    """Return ``inspect.signature(creator)``, read straight off ``__init__`` when that is where it comes from.

    Only for a class of metaclass ``type`` with no ``__signature__`` or ``__wrapped__``, whose first
    MRO entry defining ``__new__`` or ``__init__`` defines a plain-function ``__init__`` alone.
    """
    if (
        type(creator) is type
        and getattr(creator, "__signature__", None) is None
        and not hasattr(creator, "__wrapped__")
    ):
        owner = next(
            base.__dict__ for base in creator.__mro__ if "__new__" in base.__dict__ or "__init__" in base.__dict__
        )
        init = owner.get("__init__")
        if "__new__" not in owner and type(init) is types.FunctionType and not hasattr(init, "__wrapped__"):
            return inspect.signature(types.MethodType(init, creator))
    return inspect.signature(creator)


def parse_creator(creator: typing.Callable[..., typing.Any]) -> ParsedCreator:
    try:
        sig = _signature(creator)
    except (ValueError, TypeError):
        return ParsedCreator(
            return_type=SignatureItem.from_type(typing.cast(type, creator)),
            params={},
            has_positional_only_gap=False,
            accepts_any_kwargs=True,
        )

    is_class = isinstance(creator, type)
    try:
        type_hints = _class_type_hints(creator) if is_class else typing.get_type_hints(creator)
    except (NameError, TypeError) as e:
        warnings.warn(
            f"Failed to resolve type hints for {creator}: {e}. Dependency wiring will be skipped. "
            f"Pass skip_creator_parsing=True (with an explicit bound_type) to silence this warning.",
            UserWarning,
            stacklevel=2,
        )
        type_hints = {}

    params = {}
    has_positional_only_gap = False
    accepts_any_kwargs = False
    for param_name, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            accepts_any_kwargs = True
            continue
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            continue
        item = _parse_parameter(creator, param_name, param, type_hints)
        if item is None:
            has_positional_only_gap = True
            continue
        params[param_name] = item

    if is_class:
        return_sig = SignatureItem.from_type(creator)
    elif "return" in type_hints:
        return_sig = SignatureItem.from_type(type_hints["return"])
        if return_sig.unresolvable_generic is not None:
            return_sig = SignatureItem(arg_type=typing.get_origin(return_sig.unresolvable_generic))
    else:
        return_sig = SignatureItem()

    return ParsedCreator(
        return_type=return_sig,
        params=params,
        has_positional_only_gap=has_positional_only_gap,
        accepts_any_kwargs=accepts_any_kwargs,
    )
