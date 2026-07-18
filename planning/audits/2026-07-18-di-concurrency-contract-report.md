# DI-framework concurrency contract: comparative research

How do dependency-injection frameworks handle multithreaded concurrency, and
what container lifecycle do they assume? Commissioned to decide whether
modern-di's thread-safety contract — *concurrent resolution is safe; singleton
creation is locked (double-checked); configure and close happen at
single-threaded lifecycle edges* — is the field standard (document it) or
unusually narrow (consider expanding to concurrent teardown). The trigger was
a free-threaded stress test that surfaced a `RuntimeError` when a container is
closed **while** other threads resolve from it (the warm-singleton memo-swap
work, `planning/changes/2026-07-18.01`).

## Method

A fan-out research pass (6 angles, 27 sources fetched, 104 candidate claims,
25 verified by 3-vote adversarial checking — 24 confirmed, 1 refuted). Sources
are current primary docs/source unless noted: Microsoft Learn (updated
2026-03-30), Autofac latest docs, Guice master source, Spring issues/javadoc,
uber-go/dig + Fx docs, Koin releases, and the Python frameworks' own docs.
Coverage is uneven — see Caveats; absent frameworks are *unmeasured*, not
negative.

## Headline

**modern-di's build → resolve → dispose lifecycle with single-threaded
teardown is the universal field standard. No framework in the evidence set
offers concurrent disposal-during-resolution as a supported guarantee.** The
contract should be stated explicitly, not expanded.

## Findings

### 1. Concurrent teardown-during-resolution is supported nowhere (high confidence)

- **.NET** (`Microsoft.Extensions.DependencyInjection`): resolving after
  disposal *deadlocked* before .NET 6 and now throws `ObjectDisposedException`.
  Disposal is terminal, never a concurrent-safe path.
  ([compat note](https://learn.microsoft.com/en-us/dotnet/core/compatibility/extensions/6.0/service-provider-disposed))
- **Autofac**: documents thread-safe resolution *and* explicitly warns against
  teardown-under-resolution — "you must be very careful that the parent scope
  doesn't get disposed out from under the spawned thread," and "you can get
  into a bad situation where components can't be resolved if you spawn the
  thread and then dispose the parent scope."
  ([concurrency](https://docs.autofac.org/en/latest/advanced/concurrency.html),
  [instance-scope](https://docs.autofac.org/en/latest/lifetime/instance-scope.html))
- **Guice**: `SingletonScope` addresses only construction/initialization
  concurrency; there is no dispose/shutdown lifecycle at all.
  ([source](https://github.com/google/guice/blob/master/core/src/com/google/inject/internal/SingletonScope.java))
- **Uber Fx** (Go): an explicit two-phase `initialization → execution`
  lifecycle (OnStart hooks, then OnStop hooks) — build/run/teardown, not
  concurrent teardown. ([lifecycle](https://uber-go.github.io/fx/lifecycle.html))
- **Koin**: as recently as 4.2.1 had to *fix* a `Scope._closed` non-volatile
  memory-visibility bug (#2389) — even where concurrent-close state is
  contemplated, it has been a bug source, not a clean guarantee.
  ([4.2.1](https://github.com/InsertKoinIO/koin/releases/tag/4.2.1))

### 2. Concurrent resolution after build is the near-universal guarantee — construction only (high)

.NET verbatim: "Once an `IServiceProvider` or `IServiceScope` has been built,
it's safe to resolve services concurrently from multiple threads," with the
note that this "doesn't make the resolved service instances themselves
thread-safe." Autofac: "All container operations are safe for use between
multiple threads" (while resolution-context objects are single-threaded).
that-depends: Singleton is "thread-safe and async-safe." The guarantee is
scoped to the post-build phase and covers *getting* the instance, never the
instance's own thread-safety.
([.NET guidelines](https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection/guidelines))

### 3. Configure/registration is a single-threaded startup phase (high)

Autofac verbatim: "ContainerBuilder and ComponentRegistryBuilder are not
thread-safe and are designed to be used only on a single thread at the time
the application starts up." .NET's model (thread-safety applies only after the
provider/scope is built) is the same shape. This mirrors modern-di's rule that
`register`/`override`/`set_context` happen at single-threaded edges.

### 4. Singleton creation is locked, usually double-checked (high)

Guice: per-binding lock + double-checked locking over a volatile field
("double-checked locking for quick exit when scope is initialized"). .NET: the
singleton factory "is guaranteed to be called only once by a single thread"
(like a static constructor). Spring: `DefaultSingletonBeanRegistry`
synchronizes singleton access (a lenient `ReentrantLock` scheme since 6.2;
`getSingletonMutex` deprecated). that-depends: "If multiple threads call
`resolve_sync()` at the same time, the factory is only called once." This
double-checked pattern is exactly modern-di's approach.

### 5. A design mistake modern-di already avoids (high)

Both Spring and .NET hit **deadlocks from holding the singleton-creation lock
while running user factory code**. Spring #23501 verbatim: "This call into user
code while holding a lock can result in deadlock" → Spring 6.2 introduced
lenient singleton locking. .NET PR #46157 moved from a global lock to a
per-singleton-call-site lock for the same reason. modern-di already resolves
the dependency graph **outside** the lock (only creation + the cache store run
under it — `architecture/concurrency.md`), so it is on the correct side of a
bug two major frameworks had to fix.
([Spring #23501](https://github.com/spring-projects/spring-framework/issues/23501),
[.NET PR #46157](https://github.com/dotnet/runtime/pull/46157))

### 6. Python singleton thread-safety varies widely (high)

- **that-depends**: Singleton "is thread-safe and async-safe."
- **dependency-injector**: default Singleton is *NOT* thread-safe ("Otherwise
  you could trap into the race condition problem: Singleton will create
  multiple objects"); thread-safety is opt-in via `ThreadSafeSingleton` /
  `ThreadLocalSingleton`.
- **dishka**: the APP-scope container has a lock by default, but deeper
  concurrently-entered child scopes need an explicit `lock_factory` or "you
  cannot guarantee that only one instance of that object is created" — and the
  caller must pick the right lock type ("threading and asyncio locks are not
  interchangeable").

modern-di's default double-checked locking on singleton creation sits on the
safer end of this spread.
([dependency-injector](https://python-dependency-injector.ets-labs.org/providers/singleton.html),
[dishka](https://dishka.readthedocs.io/en/stable/container/index.html),
[that-depends](https://that-depends.modern-python.org/providers/singleton/))

### 7. Free-threading (PEP 703) is a near-empty field — a modern-di differentiator (medium)

Of the covered Python frameworks, **only wireup** makes an explicit no-GIL
claim: its README says it is "thread-safe, no-GIL (PEP 703) ready, and
fail-fast by design." This is a self-advertisement with **no documented locking
mechanism and no independent audit**. dishka, dependency-injector, and
that-depends make no explicit free-threading statements (that-depends documents
thread-/async-safe singletons but does not mention 3.13t/3.14t). modern-di's
Beta free-threaded support with an actual tested, documented mechanism is thus
a stronger claim than the only stated peer.
([wireup](https://github.com/maldoinc/wireup))

## What this means for modern-di

1. **Document the lifecycle contract explicitly; do not expand it.** State the
   positive model — configure (single-threaded) → resolve and child-container
   build (concurrent) → close/teardown (single-threaded) — in
   `architecture/concurrency.md`, replacing the current caveat-list framing. The
   teardown-during-resolution finding that triggered this research is an
   out-of-contract scenario by the field-standard definition; no comparable
   framework promises otherwise.
2. **The free-threaded story is a positioning edge.** An *explicit* lifecycle
   contract plus real Beta no-GIL support is a clarity advantage in a field
   that is either silent or (wireup) unaudited on PEP 703.
3. **The graph-resolves-outside-the-lock design is validated** against the
   Spring/.NET deadlock history — worth stating as a deliberate choice, not an
   accident.

## Caveats and coverage gaps

- **No surviving verified evidence** for svcs, python-injector, punq, Dagger
  (compile-time; runtime concurrency largely N/A), uber-go/dig and Fx internals
  beyond the cited issues/docs, or Koin beyond release notes/issues.
  Conclusions about those are **absent, not negative**.
- The **wireup** free-threading line is marketing, not an audit; its actual
  locking strategy is undocumented.
- One refuted claim: that Spring guards singleton creation with a *coarse
  per-registry monitor* (0-3) — the current scheme is the lenient
  `ReentrantLock` (since 6.2); exact internals are version-sensitive.
- Python framework docs move fast; verify against the installed version before
  relying on exact behavior.
- Everywhere, "thread-safe resolution" means construction/resolution only —
  never that resolved instances are themselves thread-safe.

## Open questions

- Do svcs, python-injector, punq, or the Go frameworks make any thread-safety
  or free-threaded statements, and do any support concurrent scope disposal?
- What is wireup's actual locking strategy behind its "no-GIL ready" claim, and
  has anyone tested it under 3.13t/3.14t?
- Does *any* framework, in any language, genuinely support tearing down a scope
  while other threads resolve (reference-counting, epoch/RCU, drain-then-dispose)
  — or is single-threaded teardown truly universal?
