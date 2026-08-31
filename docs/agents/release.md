# Cutting a release (maintainers)

Tag-driven via [`.github/workflows/release.yml`](../../.github/workflows/release.yml): push a
bare-semver-**named** tag off green `main` —
`git tag -m "modern-di 3.4.0" 3.4.0 && git push origin 3.4.0`. Only the tag *name* must be bare
semver (that is what the workflow matches); the tag object itself may be annotated or signed, and
`-m` is required whenever `tag.gpgsign`/`tag.forceSignAnnotated` is set — without it `git tag`
aborts with `fatal: no tag message?`. The workflow runs `just publish` (the tag sets the version
via `uv version`; no `pyproject.toml` bump) to PyPI, then creates the GitHub Release — PyPI first,
so a failed publish creates no Release. Pre-releases use the PEP 440 form (`2.0.0rc1`, not
`2.0.0-alpha.5`). PyPI is irreversible; there is no CI gate (a tag is the commitment point).

The Release body is GitHub's generated notes, built from the squashed PR titles since the previous
tag. A conventional-commit PR title is therefore the changelog entry a reader gets, and that is
where the care goes. A release wanting prose gets it after the fact with
`gh release edit <tag> --notes-file <file>`. There is no committed notes file and no template.
Releases 2.15.0 through 3.4.0 have curated bodies, which live on the
[Releases page](https://github.com/modern-python/modern-di/releases) and nowhere else.
