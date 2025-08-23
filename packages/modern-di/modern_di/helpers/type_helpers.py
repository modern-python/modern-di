import collections
import typing


GENERIC_TYPES = {
    typing.Iterator,
    typing.AsyncIterator,
    typing.Generic,
    typing.AsyncGenerator,
    collections.abc.Iterator,
    collections.abc.AsyncIterator,
    collections.abc.Generator,
    collections.abc.AsyncGenerator,
}


def define_bounded_type(creator: type | object) -> type | None:  # noqa: PLR0911
    if isinstance(creator, type):
        return creator

    type_hints = typing.get_type_hints(creator)
    return_annotation = type_hints.get("return")
    if not return_annotation:
        return None

    if isinstance(return_annotation, type):
        return return_annotation

    if typing.get_origin(return_annotation) not in GENERIC_TYPES:
        return None

    args = typing.get_args(return_annotation)
    if not args:
        return None

    if isinstance(args[0], type):
        return args[0]

    return None
