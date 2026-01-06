import dataclasses
import types
import typing


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class DependencySignature:
    dependency_type: type | None
    kwargs: dict[str, type]


def parse_signature(creator: type | object) -> DependencySignature:
    type_hints = typing.get_type_hints(creator)
    return_annotation = type_hints.pop("return", None)

    dependency_type: type | None
    if isinstance(creator, type):
        dependency_type = creator
    elif isinstance(return_annotation, type) and not isinstance(return_annotation, types.GenericAlias):
        dependency_type = return_annotation
    else:
        dependency_type = None

    return DependencySignature(
        dependency_type=dependency_type,
        kwargs=type_hints,
    )
