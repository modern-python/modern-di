import dataclasses
import inspect
import types
import typing
import warnings

from modern_di import exceptions
from modern_di.types import UNSET


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SignatureItem:
    arg_type: type | None = None
    args: list[type] = dataclasses.field(default_factory=list)
    is_nullable: bool = False
    default: object = UNSET
    raw_annotation: object = None

    @classmethod
    def from_type(cls, type_: type, default: object = UNSET) -> "SignatureItem":
        if type_ is types.NoneType:
            return cls()

        # typing.Annotated
        if hasattr(type_, "__metadata__"):
            type_ = typing.get_args(type_)[0]

        result: dict[str, typing.Any] = {"default": default}

        # union type
        if isinstance(type_, types.UnionType) or typing.get_origin(type_) is typing.Union:
            args = [typing.get_origin(x) or x for x in typing.get_args(type_)]
            if types.NoneType in args:
                result["is_nullable"] = True
                args.remove(types.NoneType)

            if len(args) > 1:
                result["args"] = args
            elif args:
                result["arg_type"] = args[0]

        # generic — parameterized generics are not resolvable by type
        elif typing.get_origin(type_) is not None:
            result["raw_annotation"] = type_

        elif isinstance(type_, type):
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
            return None  # cannot be passed by keyword; the default applies
        raise exceptions.UnsupportedCreatorParameterError(
            creator=creator,
            parameter_name=param_name,
            reason=(
                "positional-only parameters cannot be passed by keyword; "
                "give the parameter a default or use skip_creator_parsing=True"
            ),
        )

    default = UNSET
    if param.default is not param.empty:
        default = param.default

    if param_name in type_hints:
        return SignatureItem.from_type(type_hints[param_name], default=default)
    return SignatureItem(default=default)


def parse_creator(creator: typing.Callable[..., typing.Any]) -> tuple[SignatureItem, dict[str, SignatureItem]]:
    try:
        sig = inspect.signature(creator)
    except (ValueError, TypeError):
        return SignatureItem.from_type(typing.cast(type, creator)), {}

    is_class = isinstance(creator, type)
    try:
        if is_class and hasattr(creator, "__init__"):
            type_hints = typing.get_type_hints(creator.__init__)
        else:
            type_hints = typing.get_type_hints(creator)
    except (NameError, TypeError) as e:
        warnings.warn(
            f"Failed to resolve type hints for {creator}: {e}. Dependency wiring will be skipped. "
            f"Pass skip_creator_parsing=True (with an explicit bound_type) to silence this warning.",
            UserWarning,
            stacklevel=2,
        )
        type_hints = {}

    param_hints = {}
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        item = _parse_parameter(creator, param_name, param, type_hints)
        if item is not None:
            param_hints[param_name] = item

    if is_class:
        return_sig = SignatureItem.from_type(creator)
    elif "return" in type_hints:
        return_sig = SignatureItem.from_type(type_hints["return"])
        if return_sig.raw_annotation is not None:
            # a parameterized generic return type degrades to its origin for bound_type
            return_sig = SignatureItem(arg_type=typing.get_origin(return_sig.raw_annotation))
    else:
        return_sig = SignatureItem()

    return return_sig, param_hints
