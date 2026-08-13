import sys
import threading
import typing

import pytest

from modern_di import Container, Group, providers, suggester
from modern_di.exceptions import DuplicateProviderTypeError
from modern_di.providers.abstract import AbstractProvider
from modern_di.registries import providers_registry as pr_mod
from modern_di.registries.providers_registry import ProvidersRegistry
from modern_di.scope import Scope
from modern_di.types_parser import SignatureItem


def test_providers_registry_find_provider_not_found() -> None:
    providers_registry = ProvidersRegistry()
    assert providers_registry.find_provider(str) is None


def test_is_validated_defaults_false() -> None:
    registry = ProvidersRegistry()
    assert registry.is_validated() is False


def test_mark_validated_sets_validated() -> None:
    registry = ProvidersRegistry()
    registry.mark_validated()
    assert registry.is_validated() is True


def test_mutation_clears_validated() -> None:
    """INVARIANT: every registry mutation clears `_validated`.

    `register` and `add_providers` are the only mutators. One that forgets to clear leaves a stale
    clean result, so a later `validate()` returns free without walking the now-larger graph -- and
    the runtime cycle guard stays armed to re-raise instead of converting.
    """
    registry = ProvidersRegistry()
    registry.mark_validated()
    assert registry.is_validated() is True

    class _MutationTarget: ...

    registry.add_providers(providers.Factory(scope=Scope.APP, creator=_MutationTarget))
    assert registry.is_validated() is False


def test_mutation_clears_the_resolver_and_plan_memos() -> None:
    class _Dep: ...

    registry = ProvidersRegistry()
    dep_factory = providers.Factory(scope=Scope.APP, creator=_Dep, bound_type=_Dep)
    registry.add_providers(dep_factory)
    registry.resolver_for(dep_factory)  # populates _resolvers (and _plans via compile)
    assert registry._resolvers
    assert registry._plans

    class _Other: ...

    registry.add_providers(providers.Factory(scope=Scope.APP, creator=_Other, bound_type=_Other))
    assert registry._resolvers == {}  # mutation cleared the memos
    assert registry._plans == {}


def test_providers_registry_add_provider_duplicates() -> None:
    str_factory = providers.Factory(creator=lambda: "string", bound_type=str)

    providers_registry = ProvidersRegistry()
    providers_registry.add_providers(str_factory)

    with pytest.raises(DuplicateProviderTypeError, match="Provider is duplicated by type <class 'str'>") as exc:
        providers_registry.add_providers(str_factory)
    assert exc.value.provider_type is str


def test_providers_registry_register_duplicate_raises() -> None:
    str_factory = providers.Factory(creator=lambda: "string", bound_type=str)

    providers_registry = ProvidersRegistry()
    providers_registry.register(str, str_factory)

    with pytest.raises(DuplicateProviderTypeError, match="Provider is duplicated by type <class 'str'>") as exc:
        providers_registry.register(str, str_factory)
    assert exc.value.provider_type is str


class _RaceBase: ...


def test_iteration_is_safe_while_another_thread_registers() -> None:
    registry = ProvidersRegistry()
    race_types = [type(f"_Race{i}", (_RaceBase,), {}) for i in range(2000)]
    for one_type in race_types[:1000]:
        registry.register(
            one_type,
            providers.Factory(scope=Scope.APP, creator=one_type, skip_creator_parsing=True, bound_type=one_type),
        )

    errors_seen: list[BaseException] = []
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:

        def writer() -> None:
            for one_type in race_types[1000:]:
                registry.register(
                    one_type,
                    providers.Factory(
                        scope=Scope.APP, creator=one_type, skip_creator_parsing=True, bound_type=one_type
                    ),
                )

        def reader() -> None:
            try:
                for _ in range(50):
                    list(iter(registry))
                    suggester.suggest(_RaceBase, registry)
            except BaseException as e:  # noqa: BLE001  # pragma: no cover
                errors_seen.append(e)  # pragma: no cover

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    assert errors_seen == []


def test_concurrent_first_resolve_of_same_provider_does_not_false_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Thread 2 must not mistake thread 1's in-flight compile of the SAME provider for a cycle.
    # Deterministic: a stall gate holds thread 1 mid-compile while thread 2 enters the window.
    class _Leaf: ...

    class _Root:
        def __init__(self, leaf: _Leaf) -> None:
            self.leaf = leaf

    class _G(Group):
        leaf = providers.Factory(creator=_Leaf, scope=Scope.APP)
        root = providers.Factory(creator=_Root, scope=Scope.APP)

    container = Container(groups=[_G])
    container.open()
    real_compile = pr_mod.compile_resolver
    entered = threading.Event()
    release = threading.Event()
    stalled = threading.Event()

    def stalling_compile(
        provider: AbstractProvider[typing.Any], registry: pr_mod.ProvidersRegistry
    ) -> typing.Callable[[Container], typing.Any]:
        if provider is _G.root and not stalled.is_set():
            stalled.set()
            entered.set()  # thread 1's pid is now in _building
            release.wait(timeout=5)
        return real_compile(provider, registry)

    monkeypatch.setattr(pr_mod, "compile_resolver", stalling_compile)
    errors: list[BaseException] = []

    def first() -> None:
        try:
            container.resolve(_Root)
        except BaseException as exc:  # noqa: BLE001  # pragma: no cover - pre-fix path only
            errors.append(exc)

    def second() -> None:
        entered.wait(timeout=5)  # enter only once thread 1 is mid-compile of _Root
        try:
            container.resolve(_Root)
        except BaseException as exc:  # noqa: BLE001  # pragma: no cover - pre-fix path only
            errors.append(exc)
        finally:
            release.set()  # let thread 1 finish

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors  # pre-fix: thread 2 raises RecursionError (a false cycle)


class _RaceDep:
    pass


class _RaceSvc:
    def __init__(self, dep: "_RaceDep | None" = None) -> None:
        self.dep = dep


def test_mutation_during_compile_does_not_strand_a_stale_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    # `resolver_for` compiles outside `_lock` and publishes after. Without a generation check, a
    # registration landing in that window clears a memo the resolver has not entered yet, and the
    # stale resolver is then written in and never dropped -- so the registration is silently and
    # permanently lost. Driven deterministically with an event rather than by racing threads: the
    # natural race needs a deep graph to widen the window and is not a reliable gate.
    svc = providers.Factory(creator=_RaceSvc, scope=Scope.APP)

    class G(Group):
        s = svc

    container = Container(scope=Scope.APP, groups=[G])  # _RaceDep deliberately not registered yet
    compiled = threading.Event()
    may_publish = threading.Event()
    real_compile = pr_mod.compile_resolver

    def hold_open(
        provider: AbstractProvider[typing.Any], registry: ProvidersRegistry
    ) -> typing.Callable[[Container], typing.Any]:
        resolver = real_compile(provider, registry)
        if provider is svc:
            compiled.set()
            may_publish.wait(5)
        return resolver

    monkeypatch.setattr(pr_mod, "compile_resolver", hold_open)
    worker = threading.Thread(target=lambda: container.resolve_provider(svc))
    worker.start()
    try:
        assert compiled.wait(5), "compile never reached the publication window"  # pragma: no cover
        container.add_providers(providers.Factory(creator=_RaceDep, scope=Scope.APP))
    finally:
        may_publish.set()
        worker.join(5)

    # _RaceDep is registered, so a resolve must now inject it -- from a fresh resolver, because the
    # one compiled against the old registry must not have survived the invalidation.
    assert container.providers_registry.find_provider(_RaceDep) is not None
    assert isinstance(container.resolve_provider(svc).dep, _RaceDep)


def test_mutation_during_plan_build_does_not_strand_a_stale_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    # `plan_for` has the same shape as `resolver_for` -- build outside the lock, store after -- so a
    # stale wiring plan survives invalidation independently. Guarding only the resolver leaves this
    # window open, which showed up as a residual failure rate once the resolver window was closed.
    svc = providers.Factory(creator=_RaceSvc, scope=Scope.APP)

    class G(Group):
        s = svc

    container = Container(scope=Scope.APP, groups=[G])
    registry = container.providers_registry
    built = threading.Event()
    may_publish = threading.Event()
    real_build = pr_mod.WiringPlan.build

    def hold_open(
        *,
        parsed_kwargs: "dict[str, SignatureItem]",
        kwargs: "dict[str, typing.Any] | None",
        registry: ProvidersRegistry,
        owner: "providers.Factory[typing.Any]",
    ) -> pr_mod.WiringPlan:
        plan = real_build(parsed_kwargs=parsed_kwargs, kwargs=kwargs, registry=registry, owner=owner)
        if owner is svc:
            built.set()
            may_publish.wait(5)
        return plan

    monkeypatch.setattr(pr_mod.WiringPlan, "build", staticmethod(hold_open))
    worker = threading.Thread(target=lambda: registry.plan_for(svc, svc._parsed_kwargs, svc._kwargs))
    worker.start()
    try:
        assert built.wait(5), "plan build never reached the publication window"  # pragma: no cover
        container.add_providers(providers.Factory(creator=_RaceDep, scope=Scope.APP))
    finally:
        may_publish.set()
        worker.join(5)

    monkeypatch.undo()
    assert isinstance(container.resolve_provider(svc).dep, _RaceDep)
