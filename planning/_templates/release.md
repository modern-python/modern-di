# modern-di <version> — <one-line headline>

<One or two sentences: what this release is and its headline change. Say up
front if there are no behavior/API changes.>

<!-- Keep only the sections that apply; reorder/rename freely. A tiny release
     may be just the title + one section. Versioning is tag-driven — the
     release tag sets the version (`just publish` runs `uv version`), so there
     is no pyproject bump. -->

## Feature

- **<name>.** What it adds and how to use it.

## Fix

- **<name>.** What was broken, now fixed (reference the issue/regression).

## Internal refactors

- **<name>.** What changed under the hood, stated as no behavior change.

## Packaging

- Metadata / build / dependency changes visible to installers.

## Why

Context a reader needs for the headline change. Omit for small releases.

## Downstream

What integrations (FastAPI, Litestar, FastStream, Typer, `modern-di-pytest`)
must do — e.g. bump their `modern-di` floor — or "No action needed" when there
is no API change.

## Internals

- Coverage / tooling notes (e.g. 100% line coverage across Python 3.10–3.14).
