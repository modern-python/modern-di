import dataclasses
import inspect
import types
import typing

from modern_di.types import UNSET


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SignatureItem:
    arg_type: type | None = None
    args: list[type] = dataclasses.field(default_factory=list)
    is_nullable: bool = False
    default: object = UNSET

    @classmethod
    def from_type(cls, type_: type, default: object = UNSET) -> "SignatureItem":
        result: dict[str, typing.Any] = {"default": default}
        if isinstance(type_, types.GenericAlias):
            result["arg_type"] = type_.__origin__
            result["args"] = list(type_.__args__)
        elif isinstance(type_, (types.UnionType, typing._UnionGenericAlias)):  # type: ignore[attr-defined]  # noqa: SLF001
            args = list(type_.__args__)
            if types.NoneType in args:
                result["is_nullable"] = True
                args.remove(types.NoneType)
            if len(args) > 1:
                result["args"] = args
            elif args:
                result["arg_type"] = args[0]
        elif isinstance(type_, type):
            result["arg_type"] = type_
        return cls(**result)


def parse_creator(creator: typing.Callable[..., typing.Any]) -> tuple[SignatureItem, dict[str, SignatureItem]]:
    try:
        sig = inspect.signature(creator)
    except ValueError:
        return SignatureItem.from_type(typing.cast(type, creator)), {}

    param_hints = {}
    for param_name, param in sig.parameters.items():
        default = UNSET
        if param.default is not param.empty:
            default = param.default
        if param.annotation is not param.empty:
            param_hints[param_name] = SignatureItem.from_type(param.annotation, default=default)
        else:
            param_hints[param_name] = SignatureItem(default=default)
    if sig.return_annotation:
        return_sig = SignatureItem.from_type(sig.return_annotation)
    elif isinstance(creator, type):
        return_sig = SignatureItem.from_type(creator)
    else:
        return_sig = SignatureItem()

    return return_sig, param_hints
