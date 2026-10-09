# Cutting a release (maintainers)

Tag-driven via [`.github/workflows/release.yml`](../../.github/workflows/release.yml): push a
bare-semver-**named** tag off green `main` with
`git tag -m "modern-di 3.4.0" 3.4.0 && git push origin 3.4.0`. Only the tag *name* must be bare
semver (that is what the workflow matches); the tag object itself may be annotated or signed, and
`-m` is required whenever `tag.gpgsign`/`tag.forceSignAnnotated` is set. Without it `git tag`
aborts with `fatal: no tag message?`. Pre-releases use the PEP 440 form (`2.0.0rc1`, not
`2.0.0-alpha.5`). The `pypi` environment only accepts deployments from tags matching that pattern.

The workflow runs three jobs in order, and each starts only if the one before it passed:

1. `gate` fails unless the tagged commit is an ancestor of `main` and has a `push`-event run of
   [`ci.yml`](../../.github/workflows/ci.yml) that completed with `success`. It takes the latest
   such run and fails if there is none or it is still running, so wait for `main`'s CI to finish
   before you push the tag. The workflow conclusion already lets the prerelease pytest jobs fail,
   since they are `continue-on-error`. Runs from other workflows on the same commit (the nightly
   dependency check, docs deploy, benchmarks, Dependabot) do not count. The gate does not re-run
   the checks either: `just install` upgrades the dev tools, so a re-run could block a release
   over a new `ruff` or `ty` rule while the reviewed code is unchanged.
2. `publish` runs `just publish` (the tag sets the version via `uv version`; no `pyproject.toml`
   bump) and uploads to PyPI through Trusted Publishing. It holds `id-token: write` and nothing
   that can write to the repository.
3. `github-release` creates the GitHub Release with `contents: write`. PyPI goes first because an
   upload cannot be undone, so a failed publish creates no Release.

The Release body is GitHub's generated notes, built from the squashed PR titles since the previous
tag. A conventional-commit PR title is therefore the changelog entry a reader gets, and that is
where the care goes. A release wanting prose gets it after the fact with
`gh release edit <tag> --notes-file <file>`. There is no committed notes file and no template.
Releases 2.15.0 through 3.4.0 have curated bodies, which live on the
[Releases page](https://github.com/modern-python/modern-di/releases) and nowhere else.
