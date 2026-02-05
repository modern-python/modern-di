import typing

from modern_di.providers.abstract import AbstractProvider


if typing.TYPE_CHECKING:
    import typing_extensions


T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class Group:
    providers: list[AbstractProvider[typing.Any]]

    def __new__(cls, *_: typing.Any, **__: typing.Any) -> "typing_extensions.Self":  # noqa: ANN401
        msg = f"{cls.__name__} cannot not be instantiated"
        raise RuntimeError(msg)

    @classmethod
    def get_providers(cls) -> list[AbstractProvider[typing.Any]]:
        if not hasattr(cls, "providers"):
            cls.providers = [x for x in cls.__dict__.values() if isinstance(x, AbstractProvider)]

        return list(cls.providers)
