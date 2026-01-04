import typing

from modern_di import providers


if typing.TYPE_CHECKING:
    from modern_di.container import Container


T_co = typing.TypeVar("T_co", covariant=True)


def _resolve_args(container: "Container", args: list[typing.Any]) -> list[typing.Any]:
    return [container.resolve_provider(x) if isinstance(x, providers.AbstractProvider) else x for x in args]


def _resolve_kwargs(container: "Container", kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
    return {
        k: container.resolve_provider(v) if isinstance(v, providers.AbstractProvider) else v for k, v in kwargs.items()
    }


def _resolve_dict(container: "Container", provider: providers.Dict[T_co]) -> dict[str, T_co]:
    return _resolve_kwargs(container, provider.kwargs or {})


def _resolve_list(container: "Container", provider: providers.List[T_co]) -> list[T_co]:
    return _resolve_args(container, provider.args or [])


def _resolve_container(container: "Container", _: providers.ContainerProvider) -> "Container":
    return container


def _resolve_context(container: "Container", provider: providers.ContextProvider[T_co]) -> T_co | None:
    return container.context_registry.find_context(provider.context_type)


def _resolve_factory(container: "Container", provider: providers.Factory[T_co]) -> T_co:
    if (override := container.overrides_registry.fetch_override(provider.provider_id)) is not None:
        return typing.cast(T_co, override)

    args = _resolve_args(container, provider.args or [])
    kwargs = _resolve_kwargs(container, provider.kwargs or {})
    return typing.cast(T_co, provider.creator(*args, **kwargs))


def _resolve_singleton(container: "Container", provider: providers.Singleton[T_co]) -> T_co:
    if (override := container.overrides_registry.fetch_override(provider.provider_id)) is not None:
        return typing.cast(T_co, override)

    if (provider_state := container.state_registry.fetch_provider_state(provider)) is not None:
        return provider_state

    args = _resolve_args(container, provider.args or [])
    kwargs = _resolve_kwargs(container, provider.kwargs or {})

    if container.lock:
        container.lock.acquire()

    try:
        if (provider_state := container.state_registry.fetch_provider_state(provider)) is not None:
            return provider_state

        instance = typing.cast(T_co, provider.creator(*args, **kwargs))
        container.state_registry.set_provider_state(provider, instance)
        return instance
    finally:
        if container.lock:
            container.lock.release()


RESOLVERS: dict[type[providers.AbstractProvider[typing.Any]], typing.Callable[..., typing.Any]] = {
    providers.Dict: _resolve_dict,
    providers.List: _resolve_list,
    providers.ContainerProvider: _resolve_container,
    providers.ContextProvider: _resolve_context,
    providers.Factory: _resolve_factory,
    providers.Singleton: _resolve_singleton,
}
