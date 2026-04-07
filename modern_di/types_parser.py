import dataclasses
import inspect
import types
import typing
import warnings

from modern_di.types import UNSET


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SignatureItem:
    arg_type: type | None = None
    args: list[type] = dataclasses.field(default_factory=list)
    is_nullable: bool = False
    default: object = UNSET

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

            args = [typing.get_origin(arg) or arg for arg in args]

            if len(args) > 1:
                result["args"] = args
            elif args:
                result["arg_type"] = args[0]

        # generic
        elif typing.get_origin(type_) is not None:
            result["arg_type"] = typing.get_origin(type_)
            result["args"] = list(typing.get_args(type_))

        elif isinstance(type_, type):
            result["arg_type"] = type_

        return cls(**result)


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
    except NameError as e:
        warnings.warn(
            f"Failed to resolve type hints for {creator}: {e}. Dependency wiring will be skipped.",
            UserWarning,
            stacklevel=2,
        )
        type_hints = {}

    param_hints = {}
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        default = UNSET
        if param.default is not param.empty:
            default = param.default

        if param_name in type_hints:
            param_hints[param_name] = SignatureItem.from_type(type_hints[param_name], default=default)
        else:
            param_hints[param_name] = SignatureItem(default=default)

    if is_class:
        return_sig = SignatureItem.from_type(typing.cast(type, creator))
    elif "return" in type_hints:
        return_sig = SignatureItem.from_type(type_hints["return"])
    else:
        return_sig = SignatureItem()

    return return_sig, param_hints
