import inspect
import types
import typing


def parse_signature(creator: type | object) -> tuple[type | None, dict[str, type]]:
    type_hints = typing.get_type_hints(creator, include_extras=True)
    return_annotation = type_hints.pop("return", None)

    if isinstance(creator, type):
        try:
            sig = inspect.signature(creator)
            param_hints = {}
            for param_name, param in sig.parameters.items():
                if param.annotation is not param.empty:
                    param_hints[param_name] = param.annotation

            if param_hints:
                type_hints = param_hints

        except ValueError:
            pass

        dependency_type = creator
    elif isinstance(return_annotation, type) and not isinstance(return_annotation, types.GenericAlias):
        dependency_type = return_annotation
    else:
        dependency_type = None

    return dependency_type, type_hints
