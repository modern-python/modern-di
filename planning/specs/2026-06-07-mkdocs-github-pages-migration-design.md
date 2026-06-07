# Migrate docs from Read the Docs to GitHub Pages

**Date:** 2026-06-07
**Status:** Approved — ready for implementation plan

## Goal

Serve modern-di documentation at `https://modern-di.modern-python.org` from GitHub Pages instead of Read the Docs. Single rolling version, no `/latest/` URL prefix. Build runs in GitHub Actions on pushes to `main` that touch docs sources.

## Background

Current setup:

- MkDocs Material site, sources in `docs/`, config in `mkdocs.yml`.
- Built by Read the Docs via `.readthedocs.yaml`, with a custom domain (`modern-di.modern-python.org`) pointing at RTD.
- RTD serves under a `/latest/` path prefix (its version routing). One in-code URL embeds that prefix: `modern_di/errors.py:32` in `PROVIDER_DUPLICATE_TYPE_ERROR`.
- DNS for `modern-python.org` is at a registrar (not Cloudflare).

The migration moves the same MkDocs site to GitHub Pages, with a flat URL structure (no `/latest/`).

## Decisions

- **URL paths:** Drop `/latest/`. Serve at root. Update the one in-code reference in `errors.py`. No redirects.
- **Cutover:** DNS flip directly from RTD to GitHub Pages. No pre-flip verification on the github.io URL or a preview subdomain (user accepted the small-window risk; rollback is a 5-minute DNS revert).
- **Read the Docs config:** Leave `.readthedocs.yaml` in place. RTD keeps building `modern-di.readthedocs.io` as a passive fallback. A follow-up PR deletes it once GH Pages is trusted.
- **Pending `.online → .org` link edits:** Roll into the migration PR rather than committing separately.
- **Deploy mechanism:** `mkdocs gh-deploy --force` (force-push built site to a `gh-pages` branch). Chosen for simplicity and easy local rescue over the Actions-native `upload-pages-artifact` / `deploy-pages` flow.
- **Versioning:** None. No `mike` plugin. Single rolling version.

## Repo changes (this PR)

### 1. New workflow `.github/workflows/docs.yml`

```yaml
name: Deploy docs
on:
  push:
    branches: [main]
    paths:
      - "docs/**"
      - "mkdocs.yml"
      - "docs/requirements.txt"
      - ".github/workflows/docs.yml"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r docs/requirements.txt
      - run: mkdocs gh-deploy --force
```

`fetch-depth: 0` is required because `gh-deploy` needs full history to push to `gh-pages`. `--force` overwrites the `gh-pages` branch each run. Listing `docs/requirements.txt` under `paths:` is redundant (covered by `docs/**`) but kept for visibility.

### 2. `mkdocs.yml`

Already has `site_url: https://modern-di.modern-python.org` in the working tree (uncommitted). Keep as-is. No further changes.

### 3. `modern_di/errors.py:32`

Drop `/latest/` from the troubleshooting URL embedded in `PROVIDER_DUPLICATE_TYPE_ERROR`:

```python
"See https://modern-di.modern-python.org/troubleshooting/duplicate-type-error/ for more details"
```

### 4. `Justfile`

Add a local-deploy escape hatch:

```just
docs-deploy:
    uv run mkdocs gh-deploy --force
```

### 5. `README.md` and `pyproject.toml`

Already updated to `.org` in the working tree (uncommitted). Keep as-is.

## Out-of-repo steps (user-side)

Performed by the user after merging the PR.

1. **Merge & push.** First push to `main` triggers the workflow, which creates the `gh-pages` branch and pushes the built site.
2. **GitHub repo Settings → Pages**
   - Source: Deploy from a branch
   - Branch: `gh-pages` / `/ (root)`
   - Custom domain: `modern-di.modern-python.org` (writes a `CNAME` file to `gh-pages`)
   - Enforce HTTPS: tick once the certificate is provisioned (a few minutes after DNS resolves)
3. **DNS at registrar**
   - Remove the existing `modern-di` CNAME pointing at RTD
   - Add CNAME: host `modern-di` → value `modern-python.github.io.`
4. **Wait.** DNS propagation + Let's Encrypt provisioning: typically 5–30 minutes.
5. **Sanity check.** Load `https://modern-di.modern-python.org`, verify navigation, click through the troubleshooting link emitted from `errors.py`.

## What is NOT in this PR

- `.readthedocs.yaml` — left in place; deleted in a follow-up PR.
- `docs/context7.json` — still points at the `modern-di_readthedocs_io` source on context7. Update via the context7 dashboard separately when desired.
- Documentation versioning (`mike`) — explicitly out of scope.

## Verification (post-merge)

1. Workflow run for `.github/workflows/docs.yml` completes green.
2. `git ls-remote --heads origin gh-pages` shows the new branch.
3. After DNS swap, `dig modern-di.modern-python.org CNAME +short` returns `modern-python.github.io.`.
4. `curl -I https://modern-di.modern-python.org/` returns 200 with a valid certificate.
5. The troubleshooting URL emitted by `errors.py` resolves to the live troubleshooting page.

## Rollback

- DNS-level: revert the `modern-di` CNAME to RTD's target. Recovery in ~5 minutes once DNS propagates.
- Repo-level (if reverting permanently): delete the workflow, delete the `gh-pages` branch (`git push origin --delete gh-pages`), re-revert the link edits if desired. RTD config is untouched, so RTD resumes serving the custom domain immediately.

## Risks

- **DNS flip is destructive.** No pre-flip verification means a misconfigured CNAME target or missing GH Pages custom-domain entry leaves the subdomain broken until corrected. Rollback path is the DNS revert above.
- **Old `/latest/` external links 404.** Previously released package versions still embed the `/latest/` URL in their `errors.py`. Out-of-repo links (blog posts, etc.) likewise break. Accepted; no redirect layer added.
- **`gh-pages` branch creation.** The repo currently has no `gh-pages` branch, so the first `gh-deploy --force` creates it cleanly. If a `gh-pages` branch is created out-of-band before merge, this assumption breaks.

## Follow-up work (separate PRs)

- Delete `.readthedocs.yaml`.
- Update `docs/context7.json` once the docs are re-indexed at the new domain.
