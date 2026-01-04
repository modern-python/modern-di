import types
import typing


def define_bound_type(creator: type | object) -> type | None:
    if isinstance(creator, type):
        return creator

    type_hints = typing.get_type_hints(creator)
    return_annotation = type_hints.get("return")
    if not return_annotation:
        return None

    if isinstance(return_annotation, type) and not isinstance(return_annotation, types.GenericAlias):
        return return_annotation

    return None
