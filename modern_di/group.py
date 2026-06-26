import typing

from modern_di import exceptions
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    import typing_extensions


class Group:
    def __new__(cls, *_: typing.Any, **__: typing.Any) -> "typing_extensions.Self":  # noqa: ANN401
        raise exceptions.GroupInstantiationError(group_name=cls.__name__)

    @classmethod
    def get_named_providers(cls) -> dict[str, AbstractProvider[typing.Any]]:
        seen_names: set[str] = set()
        collected: dict[str, AbstractProvider[typing.Any]] = {}
        for klass in cls.__mro__:
            if klass is Group or klass is object:
                continue
            for name, value in klass.__dict__.items():
                if name in seen_names:
                    continue
                seen_names.add(name)
                if isinstance(value, AbstractProvider):
                    collected[name] = value
        return collected

    @classmethod
    def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
        seen_names: set[str] = set()
        collected: list[AbstractProvider[typing.Any]] = []
        for klass in cls.__mro__:
            if klass is Group or klass is object:
                continue
            for name, value in klass.__dict__.items():
                if name in seen_names:
                    continue
                seen_names.add(name)
                if isinstance(value, AbstractProvider):
                    collected.append(value)
        return collected
