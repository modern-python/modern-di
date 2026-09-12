# The `@inject` asymmetry is inherent

**Decision:** the four integrations that resolve `FromDI` without a decorator (fastapi, litestar,
faststream, taskiq) and the eight that require `@inject` keep their shapes. An adapter can drop
`@inject` only where the host evaluates a parameter default as a provider, and the eight offer no
such seam.

**Why:** fastapi (`Depends`), litestar (`Provide`), faststream (`Depends`) and taskiq
(`TaskiqDepends`) have a per-parameter provider hook. flask, starlette, aiohttp, celery, arq, typer
and grpc hand the handler a plain callable with a fixed signature; aiogram's `data` dict matches
kwargs by name and never evaluates a default. The defensible claim is therefore "no `@provide`
ever, and no `@inject` in the four biggest integrations", not "decorator-free". The minimal
quickstart floor follows from the same facts (7 DI lines, plus one for `@inject`, plus one where
the root open is the caller's), so there is no separate quickstart fix.
