import typing

from modern_di import exceptions
from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    import typing_extensions


T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class Group:
    providers: list[AbstractProvider[typing.Any]]

    def __new__(cls, *_: typing.Any, **__: typing.Any) -> "typing_extensions.Self":  # noqa: ANN401
        raise exceptions.GroupInstantiationError(group_name=cls.__name__)

    @classmethod
    def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
        if not hasattr(cls, "providers"):
            cls.providers = [x for x in cls.__dict__.values() if isinstance(x, AbstractProvider)]

        return list(cls.providers)
