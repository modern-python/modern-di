#!/usr/bin/env bash
# Usage: check-runs-green.sh <commit-sha>. Needs GH_TOKEN and GITHUB_REPOSITORY.
set -euo pipefail

sha="$1"
api="https://api.github.com/repos/${GITHUB_REPOSITORY}"
# The prerelease pytest matrix jobs are continue-on-error in _checks.yml.
allowed_to_fail='^checks / pytest \([^,]+, true\)$'

get_all() {
  local url="$1" key="$2" page=1 batch
  while :; do
    batch="$(curl -fsS --retry 3 \
      -H "Authorization: Bearer ${GH_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      "${url}&per_page=100&page=${page}" | jq -c ".${key}[]")"
    [[ -z "$batch" ]] && break
    printf '%s\n' "$batch"
    [[ "$(wc -l <<<"$batch")" -lt 100 ]] && break
    page=$((page + 1))
  done
}

release_run_ids="$(get_all "${api}/actions/workflows/release.yml/runs?head_sha=${sha}" workflow_runs | jq -s -c 'map(.id)')"

runs="$(get_all "${api}/commits/${sha}/check-runs?filter=latest" check_runs |
  jq -s -c --argjson skip "$release_run_ids" '
    def run_id: (.details_url // "" | capture("/actions/runs/(?<id>[0-9]+)/").id | tonumber) // null;
    map(select(run_id as $id | $id == null or ($skip | index($id) == null)))')"

jq -r '.[] | [.name, .status, (.conclusion // "-")] | @tsv' <<<"$runs" | sort

if [[ "$(jq 'map(select(.name | startswith("checks / "))) | length' <<<"$runs")" -eq 0 ]]; then
  echo "::error::no CI check runs found for ${sha}"
  exit 1
fi

bad="$(jq -r --arg allowed "$allowed_to_fail" '
  .[]
  | select(.status != "completed"
           or ((.conclusion == "success" or .conclusion == "skipped") | not)
              and (.name | test($allowed) | not))
  | "\(.name): \(.status) \(.conclusion // "")"' <<<"$runs")"

if [[ -n "$bad" ]]; then
  echo "::error::CI is not green for ${sha}"
  printf '%s\n' "$bad"
  exit 1
fi
echo "CI is green for ${sha}"
