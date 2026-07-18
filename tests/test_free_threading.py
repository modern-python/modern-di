"""Free-threaded (PEP 703) correctness: concurrent resolution shares singletons.

Hand-rolled thread stress (no plugin dependency) so it runs on every interpreter.
Under the GIL it passes trivially but still exercises the double-checked cache lock
and the setdefault-shared CacheItem; on a 3.14t build it runs those paths GIL-free.
The free-threaded *interpreter* assertion lives in CI (_checks.yml), not here, to
keep this suite version-agnostic and 100%-line-covered on every build.
See architecture/concurrency.md.
"""

import threading

from modern_di import Container, Group, Scope, providers


class _Leaf: ...


class _Mid:
    def __init__(self, leaf: _Leaf) -> None:
        self.leaf = leaf


class _Top:
    def __init__(self, mid: _Mid) -> None:
        self.mid = mid


class _RequestObj:
    def __init__(self, top: _Top) -> None:
        self.top = top


class _StressGroup(Group):
    leaf = providers.Factory(creator=_Leaf, scope=Scope.APP, cache=True)
    mid = providers.Factory(creator=_Mid, scope=Scope.APP, cache=True)
    top = providers.Factory(creator=_Top, scope=Scope.APP, cache=True)
    request_obj = providers.Factory(creator=_RequestObj, scope=Scope.REQUEST)


def test_concurrent_resolution_shares_app_singletons() -> None:
    container = Container(groups=[_StressGroup], validate=True)
    n = 32
    barrier = threading.Barrier(n)
    top_results: list[_Top | None] = [None] * n
    request_ok: list[bool] = [False] * n
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        barrier.wait()  # release all threads into resolution at once to maximize contention
        try:
            top = container.resolve(_Top)  # APP singleton: one instance shared tree-wide
            top_results[i] = top
            with container.build_child_container(scope=Scope.REQUEST) as child:
                obj = child.resolve(_RequestObj)  # REQUEST obj wiring the shared APP singleton
                request_ok[i] = obj.top is top  # child sees the same APP instance
        except BaseException as exc:  # noqa: BLE001  # pragma: no cover - a race would surface here
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len({id(result) for result in top_results}) == 1  # exactly one shared APP singleton
    assert all(request_ok)  # every child resolved that same singleton through its request object
