import collections
import types
import typing


GENERIC_TYPES = {
    typing.Iterator,
    typing.AsyncIterator,
    collections.abc.Iterator,
    collections.abc.AsyncIterator,
}


def define_bound_type(creator: type | object) -> type | None:
    if isinstance(creator, type):
        return creator

    type_hints = typing.get_type_hints(creator)
    return_annotation = type_hints.get("return")
    if not return_annotation:
        return None

    if isinstance(return_annotation, type) and not isinstance(return_annotation, types.GenericAlias):
        return return_annotation

    if typing.get_origin(return_annotation) not in GENERIC_TYPES:
        return None

    args = typing.get_args(return_annotation)
    if not args:
        return None

    return typing.cast(type, args[0])
