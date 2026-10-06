"""Static typing contracts, checked by `ty` in `just lint`; at runtime `assert_type` is a no-op."""

import typing

import pytest

from modern_di import Container, Scope, exceptions, providers


class _Base:
    closed = False


class _Sub(_Base):
    pool: typing.ClassVar[list[str]] = []


def _make_base() -> _Base:
    return _Base()


def _release_sub(sub: _Sub) -> None:
    sub.pool.clear()


def test_context_provider_without_default_is_typed_as_the_context_type() -> None:
    typing.assert_type(providers.ContextProvider(int), providers.ContextProvider[int])


def test_context_provider_with_a_typed_default_is_typed_as_the_context_type() -> None:
    typing.assert_type(providers.ContextProvider(int, default=0), providers.ContextProvider[int])


def test_context_provider_with_default_none_is_typed_as_optional() -> None:
    provider = providers.ContextProvider(int, default=None, scope=Scope.APP)
    typing.assert_type(provider, providers.ContextProvider[int | None])
    with Container(groups=[]) as container:
        typing.assert_type(container.resolve_provider(provider), int | None)
        assert container.resolve_provider(provider) is None


def test_cache_settings_rejects_a_finalizer_for_a_narrower_type() -> None:
    settings = providers.CacheSettings(finalizer=_release_sub)
    typing.assert_type(settings, providers.CacheSettings[_Sub])
    factory = providers.Factory(_make_base, cache=settings)  # ty: ignore[invalid-argument-type]
    container = Container()
    container.resolve_provider(factory)
    with pytest.raises(exceptions.FinalizerError) as exc_info:
        container.close_sync()
    assert isinstance(exc_info.value.exceptions[0], AttributeError)


def test_cache_settings_accepts_a_finalizer_for_a_wider_type() -> None:
    released: list[object] = []
    settings: providers.CacheSettings[_Base] = providers.CacheSettings(finalizer=released.append)
    factory = providers.Factory(_make_base, cache=providers.CacheSettings(finalizer=released.append))
    typing.assert_type(factory, providers.Factory[_Base])
    with Container() as container:
        instance = container.resolve_provider(providers.Factory(_make_base, cache=settings))
    assert released == [instance]


def test_cache_settings_accepts_a_finalizer_for_the_creator_type() -> None:
    def close_base(base: _Base) -> None:
        base.closed = True

    factory = providers.Factory(_make_base, cache=providers.CacheSettings(finalizer=close_base))
    typing.assert_type(factory, providers.Factory[_Base])
    with Container() as container:
        instance = container.resolve_provider(factory)
    assert instance.closed
