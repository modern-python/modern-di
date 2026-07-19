# DI static-analysis & type-safety surface — research report (2026-07-19)

## 1. Summary

**Question.** Should modern-di add a static / compile-time dependency-graph
safety net — an opt-in mypy/pyright/`ty` plugin or a richer statically-checkable
API — on top of its opt-in runtime `validate()`? What do Python peers and
cross-language frameworks do, verified against current (2026) primary sources?

**Answer.** No. Static/compile-time wiring verification is a property of
compiled-language, toolchain-heavy ecosystems; where it exists it is framed as a
*replacement* for exactly the runtime verification modern-di already ships; and a
Python type-checker plugin is infeasible for a conservative zero-dependency
library. The one in-constraint win — injection markers that type-check to the
concrete `T` — modern-di already has. Full rationale and the resulting call:
[decision](../decisions/2026-07-19-no-static-wiring-checker.md).

**Method.** A deep-research pass (6 search angles, 25 sources fetched, 102 claims
extracted, top 25 adversarially verified by 3-vote — 25 confirmed, 0 refuted).
The verified set landed entirely on axis 1 (compile-time verification in
JVM/Go/.NET/Angular/Spring). Axis-2 facts (Python type-checker plugin
feasibility) are sourced below from **primary docs and maintainer statements**
but were **not** run through the 3-vote verifier — they are marked as such.

## 2. Findings

### Axis 1 — compile-time / type-check-time verification (adversarially verified)

- **Dagger 2 (annotation processor) — true compile-time, whole-graph.** "The
  Dagger annotation processor is strict and will cause a compiler error if any
  bindings are invalid or incomplete"; validation happens "at the `@Component`
  level," not per-binding. Verified 3-0. Source:
  <https://dagger.dev/dev-guide/>.
- **Google Wire (Go, build-time codegen) — compile-time.** You write the injector
  signature; Wire generates the body via `go generate`, matching providers by Go
  static type identity, "without runtime state or reflection," so "forgetting a
  dependency becomes a compile-time error" (`no provider found for ConnectionInfo…`).
  Verified 3-0. Sources: <https://github.com/google/wire/blob/main/docs/guide.md>,
  <https://go.dev/blog/wire>.
- **Koin K2 compiler plugin — shipped, and a *replacement* for runtime verify.**
  GA "Koin Compiler 1.0" (June 2026; v1.0.2 2026-07-10), a native K2 plugin
  (not the deprecated koin-ksp-compiler), validating per-module, at `startKoin`,
  and at every `get<T>()`/`inject<T>()` call site (missing definitions, qualifier
  mismatches, scope violations, cycles). Its docs: "The compiler plugin replaces
  runtime verification. You can remove your verification tests"; `checkModules()`
  deprecated since Koin 4.0. **The single most decision-relevant finding** —
  compile-time validation is positioned to *replace*, not extend, the runtime
  `verify()` that `validate()` is modern-di's analogue of. Verified 3-0. Sources:
  <https://insert-koin.io/docs/reference/koin-compiler/compile-safety/>,
  <https://insert-koin.io/docs/setup/compiler-plugin/>.
- **Angular — one narrow compiler check; the headline is runtime.**
  `strictInjectionParameters` elevates an un-inferable `@Injectable` constructor
  param from warning to compiler error, but "no provider" (NG0201) is a runtime
  `NullInjectorError` at injection time. Verified 3-0. Sources:
  <https://angular.dev/reference/configs/angular-compiler-options>,
  <https://angular.dev/errors/NG0201>.
- **.NET built-in DI — runtime scope validation only.** `validateScopes:true` /
  `ValidateOnBuild` throw `InvalidOperationException` ("Cannot consume scoped
  service Bar from singleton Foo") at build/startup; no Roslyn analyzer in the
  platform. Compile-time coverage exists only as low-adoption third-party Roslyn
  analyzers (e.g. `DependencyInjection.Lifetime.Analyzers`). Verified 3-0 (built-in),
  medium-confidence (third-party). Source:
  <https://learn.microsoft.com/en-us/dotnet/core/extensions/dependency-injection/guidelines>.
- **Spring — IDE-only or runtime, never the compiler.** Missing/ambiguous-bean
  autowiring errors are an IntelliJ inspection (`SpringJavaInjectionPointsAutowiringInspection`)
  or a startup `NoSuchBeanDefinitionException`; javac succeeds regardless.
  Verified 3-0. Source:
  <https://www.jetbrains.com/help/inspectopedia/SpringJavaInjectionPointsAutowiringInspection.html>.

**Axis-1 takeaway:** every genuine static net is a compiled-language toolchain
artifact (annotation processor, codegen CLI, or native compiler plugin); the
runtime/startup model modern-di uses is the mainstream standard, corroborated by
.NET and Spring.

### Axis 2 — Python type-checker plugin feasibility (primary sources, not 3-voted)

- **mypy** has a plugin API (subclass `mypy.plugin.Plugin`; used by
  Django-stubs, Pydantic, SQLAlchemy) but documents it as "experimental and prone
  to change," with "backwards incompatible changes … without a deprecation
  period," advising authors to contact core devs first. Source:
  <https://mypy.readthedocs.io/en/stable/extending_mypy.html>.
- **pyright** supports no third-party plugins, by explicit maintainer decision
  (cross-checker breakage, distribution/maintenance, security of downloaded code);
  its stated alternative is standardized typing extensions (e.g.
  `dataclass_transform`/PEP 681). Sources: pyright#607, #637, and
  <https://github.com/microsoft/pyright/blob/main/docs/mypy-comparison.md>.
- **`ty`** (Astral — the checker modern-di itself uses) has no plugin system;
  astral-sh/ty#291 (reimplement mypy plugins) closed "not planned"; Astral names
  Pydantic/Django as *native* priorities. Source: astral-sh/ty#291;
  <https://astral.sh/blog/ty>.

**Axis-2 takeaway:** an opt-in modern-di checker plugin could target only mypy, be
a permanent liability against an unstable API, and would not serve modern-di's own
`ty` toolchain.

### Axis 3 — typed-API inference (primary sources, not 3-voted)

- **dishka** `FromDishka[T]` is an `Annotated` alias, so `service: FromDishka[Service]`
  type-checks cleanly as `Service`. Source: <https://github.com/reagento/dishka>.
- **dependency-injector**'s `Provider[Animal]` annotation makes mypy infer the
  base type `Animal`, not the concrete subtype; it ships a mypy-typing page.
  Source: <https://python-dependency-injector.ets-labs.org/providers/typing_mypy.html>.
- **FastAPI**'s bare `x = Depends(fn)` returns `Any`; the concrete type is
  preserved only via the `Annotated[T, Depends(fn)]` spelling. Source: FastAPI#4750.
- **modern-di** already occupies the front of this axis: `resolve(type[T]) -> T`
  and `Annotated[T, from_di(dep)]` both preserve the concrete static type — the
  same clean shape as dishka's `FromDishka[T]`.

## 3. Caveats

- **Scope of verification.** Only axis-1 claims went through the 3-vote adversarial
  verifier. Axis-2/3 facts rest on the cited primary sources without that second
  pass — strong (official docs, maintainer statements) but not verifier-hardened.
- **Vendor sourcing.** Koin's "replaces verify()" framing is vendor-published and
  softened to "in most cases," with documented incremental-compilation staleness.
- **Time-sensitivity.** Koin compile-safety is very recent (GA June 2026); FastAPI
  `Depends` typing and the .NET third-party analyzer drift across releases.

## 4. Decision-relevant conclusion

A static layer would duplicate `validate()` (Koin's own positioning), serve only
mypy users against an experimental API, and miss modern-di's own `ty` toolchain —
at cost to the zero-dep and conservative constraints. The typed-marker win is
already banked. Outcome:
[no static wiring checker](../decisions/2026-07-19-no-static-wiring-checker.md).
