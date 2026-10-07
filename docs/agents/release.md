# Cutting a release (maintainers)

Tag-driven via [`.github/workflows/release.yml`](../../.github/workflows/release.yml): push a
bare-semver-**named** tag off green `main` with
`git tag -m "modern-di 3.4.0" 3.4.0 && git push origin 3.4.0`. Only the tag *name* must be bare
semver (that is what the workflow matches); the tag object itself may be annotated or signed, and
`-m` is required whenever `tag.gpgsign`/`tag.forceSignAnnotated` is set. Without it `git tag`
aborts with `fatal: no tag message?`. Pre-releases use the PEP 440 form (`2.0.0rc1`, not
`2.0.0-alpha.5`). The `pypi` environment only accepts deployments from tags matching that pattern.

The workflow runs three jobs in order, and each starts only if the one before it passed:

1. `gate` fails unless the tagged commit is an ancestor of `main` and the CI that already ran on
   that commit is green. It reads the commit's check runs through the API
   ([`.github/scripts/check-runs-green.sh`](../../.github/scripts/check-runs-green.sh)) and needs
   every one, from any workflow, to be completed with `success` or `skipped`. The prerelease
   pytest jobs (3.15, 3.15t) may fail, as they may in CI. It also fails if no `checks / ...` runs exist or one is still
   running, so wait for `main`'s CI to finish before you push the tag. It does not re-run the
   checks: `just install` upgrades the dev tools, so a re-run could block a release over a new
   `ruff` or `ty` rule while the reviewed code is unchanged.
2. `publish` runs `just publish` (the tag sets the version via `uv version`; no `pyproject.toml`
   bump) and uploads to PyPI through Trusted Publishing. It holds `id-token: write` and nothing
   that can write to the repository.
3. `github-release` creates the GitHub Release with `contents: write`. PyPI goes first, so a failed
   publish creates no Release.

PyPI is irreversible. The tag is the commitment point.

The Release body is GitHub's generated notes, built from the squashed PR titles since the previous
tag. A conventional-commit PR title is therefore the changelog entry a reader gets, and that is
where the care goes. A release wanting prose gets it after the fact with
`gh release edit <tag> --notes-file <file>`. There is no committed notes file and no template.
Releases 2.15.0 through 3.4.0 have curated bodies, which live on the
[Releases page](https://github.com/modern-python/modern-di/releases) and nowhere else.
