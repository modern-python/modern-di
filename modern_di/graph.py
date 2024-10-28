import typing

from modern_di import Container
from modern_di.resolvers import AbstractResolver, BaseCreatorResolver


if typing.TYPE_CHECKING:
    import typing_extensions


T = typing.TypeVar("T")
P = typing.ParamSpec("P")


class BaseGraph:
    resolvers: dict[str, AbstractResolver[typing.Any]]

    def __new__(cls, *_: typing.Any, **__: typing.Any) -> "typing_extensions.Self":  # noqa: ANN401
        msg = f"{cls.__name__} cannot not be instantiated"
        raise RuntimeError(msg)

    @classmethod
    def get_resolvers(cls) -> dict[str, AbstractResolver[typing.Any]]:
        if not hasattr(cls, "resolvers"):
            cls.resolvers = {k: v for k, v in cls.__dict__.items() if isinstance(v, AbstractResolver)}

        return cls.resolvers

    @classmethod
    async def async_resolve_creators(cls, container: Container) -> None:
        for resolver in cls.get_resolvers().values():
            if isinstance(resolver, BaseCreatorResolver) and resolver.scope == container.scope:
                await resolver.async_resolve(container)

    @classmethod
    def sync_resolve_creators(cls, container: Container) -> None:
        for resolver in cls.get_resolvers().values():
            if isinstance(resolver, BaseCreatorResolver) and resolver.scope == container.scope:
                resolver.sync_resolve(container)
