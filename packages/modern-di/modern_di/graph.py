import typing

from modern_di import Container
from modern_di.providers.abstract import AbstractCreatorProvider, AbstractProvider


if typing.TYPE_CHECKING:
    import typing_extensions


T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class BaseGraph:
    providers: dict[str, AbstractProvider[typing.Any]]

    def __new__(cls, *_: typing.Any, **__: typing.Any) -> "typing_extensions.Self":  # noqa: ANN401
        msg = f"{cls.__name__} cannot not be instantiated"
        raise RuntimeError(msg)

    @classmethod
    def get_providers(cls) -> dict[str, AbstractProvider[typing.Any]]:
        if not hasattr(cls, "providers"):
            cls.providers = {k: v for k, v in cls.__dict__.items() if isinstance(v, AbstractProvider)}

        return cls.providers

    @classmethod
    async def async_resolve_creators(cls, container: Container) -> None:
        for provider in cls.get_providers().values():
            if isinstance(provider, AbstractCreatorProvider) and provider.scope == container.scope:
                await provider.async_resolve(container)

    @classmethod
    def sync_resolve_creators(cls, container: Container) -> None:
        for provider in cls.get_providers().values():
            if isinstance(provider, AbstractCreatorProvider) and provider.scope == container.scope:
                provider.sync_resolve(container)
