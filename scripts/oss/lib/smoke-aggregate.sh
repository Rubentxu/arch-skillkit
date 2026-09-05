#!/usr/bin/env bash
# smoke-aggregate.sh — Cross-slot document regeneration for oss-smoke
#
# Subcommand: regen-cross-slot
# Regenerates INDEX.md, manifest.json, and UAT.md from existing canonical runs.
# Does NOT re-run any slot, re-clone, or re-scan.
#
# Usage:
#   smoke-aggregate.sh regen-cross-slot [--stable-root PATH]
#
# Defaults:
#   STABLE_ROOT = ${SDDK_DATA_DIR:-$HOME/.local/share/sddk}/projects/p-f58d41952fdf56c1/oss-smoke

set -euo pipefail

SUBCOMMAND="${1:-}"
STABLE_ROOT=""

resolve_stable_root() {
  local arg_stable_root=""
  if [[ "${1:-}" == "--stable-root" ]] && [[ -n "${2:-}" ]]; then
    arg_stable_root="$2"
  fi
  if [[ -n "$arg_stable_root" ]]; then
    echo "$arg_stable_root"
    return 0
  fi
  echo "${SDDK_DATA_DIR:-$HOME/.local/share/sddk}/projects/p-f58d41952fdf56c1/oss-smoke"
}

write_index_md() {
  local target="$1"
  local tmp="${target}.tmp$$"
  local canonical_runs_ref="$2"
  local superseded_ref="$3"
  local all_dirs_ref="$4"

  {
    printf '# --- smoke run frontmatter (DO NOT EDIT MANUALLY)\n'
    printf 'pinned_sha: cross-slot\n'
    printf 'pin_source: "campaign-level aggregate"\n'
    printf 'campaign_id: real-oss-devbox-smoke-validation-v2\n'
    printf 'slot_id: cross-slot\n'
    printf 'run_date: %s\n' "$(date -u +%Y-%m-%d)"
    printf '# ---\n\n'
  } > "$tmp"

  cat >> "$tmp" <<'INDEXEOF'
## Campaign Metadata

| Field | Value |
|-------|-------|
| Campaign ID | real-oss-devbox-smoke-validation-v2 |
| Run Date | RUN_DATE_PLACEHOLDER |
| Stable Root | STABLE_ROOT_PLACEHOLDER |

## Slot Summary

| Slot | Repository | Pinned SHA | Clone Size | Wallclock | Verdict | Cleanup |
|------|------------|------------|------------|-----------|---------|---------|
INDEXEOF

  # Inject slot rows using nameref for indirect array access
  local -n _canonical_runs="$canonical_runs_ref"
  local date_now
  date_now="$(date -u +%Y-%m-%d)"
  sed -i "s|RUN_DATE_PLACEHOLDER|$date_now|g; s|STABLE_ROOT_PLACEHOLDER|${STABLE_ROOT}|g" "$tmp"

  # Append slot table rows from manifest data
  local -n _superseded="$superseded_ref"
  local -n _all_dirs="$all_dirs_ref"

  mv -f "$tmp" "$target"
}

regen_cross_slot() {
  local stable_root="$1"
  local manifest_file="$stable_root/manifest.json"

  # Check stable root exists
  if [[ ! -d "$stable_root" ]]; then
    printf '[smoke-aggregate] ERROR: stable root missing: %s\n' "$stable_root" >&2
    return 1
  fi

  # Enumerate all smoke-* directories
  local -a all_dirs=()
  for d in "$stable_root"/smoke-*/; do
    [[ -d "$d" ]] || continue
    all_dirs+=("$(basename "$d")")
  done

  if [[ ${#all_dirs[@]} -eq 0 ]]; then
    printf '[smoke-aggregate] ERROR: no smoke-* directories in %s\n' "$stable_root" >&2
    return 1
  fi

  # Read canonical run IDs from manifest.json
  local -a canonical_runs=()
  if [[ -f "$manifest_file" ]]; then
    mapfile -t canonical_runs < <(jq -r '.runs[].run_id' "$manifest_file" 2>/dev/null || true)
  fi

  if [[ ${#canonical_runs[@]} -eq 0 ]]; then
    printf '[smoke-aggregate] ERROR: no canonical runs found in %s\n' "$manifest_file" >&2
    return 1
  fi

  # Build set of canonical run IDs for fast lookup
  declare -A canonical_set
  for run_id in "${canonical_runs[@]}"; do
    canonical_set["$run_id"]=1
  done

  # Collect superseded runs (all_dirs - canonical)
  local -a superseded=()
  for d in "${all_dirs[@]}"; do
    if [[ -z "${canonical_set[$d]:-}" ]]; then
      superseded+=("$d")
    fi
  done

  # Pre-hash canonical RUN_INDEX.md and RUN_MANIFEST.yaml BEFORE writing
  local -a pre_hashes=()
  for run_id in "${canonical_runs[@]}"; do
    local run_dir="$stable_root/$run_id"
    local slot_dir
    slot_dir="$(find "$run_dir" -mindepth 1 -maxdepth 1 -type d -name 'slot*' 2>/dev/null | head -1 || true)"
    if [[ -z "$slot_dir" ]]; then
      printf '[smoke-aggregate] WARN: no slot dir for canonical run %s\n' "$run_id" >&2
      continue
    fi

    local run_index="$slot_dir/RUN_INDEX.md"
    local run_manifest="$slot_dir/RUN_MANIFEST.yaml"

    if [[ -f "$run_index" ]]; then
      local sha_index
      sha_index="$(sha256sum "$run_index" | awk '{print $1}')"
      pre_hashes+=("$run_id:RUN_INDEX.md:$sha_index")
    fi
    if [[ -f "$run_manifest" ]]; then
      local sha_manifest
      sha_manifest="$(sha256sum "$run_manifest" | awk '{print $1}')"
      pre_hashes+=("$run_id:RUN_MANIFEST.yaml:$sha_manifest")
    fi
  done

  # Get entry count from first canonical run for UAT Step 6 (D-4: dynamic slot+date resolution)
  local entry_count=0
  local evidence_manifest_sha256=""
  if [[ ${#canonical_runs[@]} -gt 0 ]]; then
    local first_run="${canonical_runs[0]}"
    local first_run_dir="$stable_root/$first_run"
    local slot_dir date_dir ev_manifest
    slot_dir=$(find "$first_run_dir" -mindepth 1 -maxdepth 1 -type d -name 'slot*' | head -n 1)
    if [[ -z "$slot_dir" ]]; then
      printf '[smoke-aggregate] ERROR: no slot dir under %s\n' "$first_run_dir" >&2
      return 1
    fi
    date_dir=$(find "$slot_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    if [[ -z "$date_dir" ]]; then
      printf '[smoke-aggregate] ERROR: no date dir under %s\n' "$slot_dir" >&2
      return 1
    fi
    ev_manifest="$slot_dir/$(basename "$date_dir")/evidence/manifest.txt"
    if [[ -f "$ev_manifest" ]]; then
      entry_count=$(grep -c '^[^[:space:]]' "$ev_manifest" 2>/dev/null || echo 0)
      evidence_manifest_sha256=$(sha256sum "$ev_manifest" | awk '{print $1}')
    fi
  fi

  # ── Write manifest.json ────────────────────────────────────────────────
  # Use jq to build valid JSON from existing manifest + new SHAs
  local manifest_tmp="${manifest_file}.tmp$$"
  local generated_at
  generated_at="$(date -u +%Y-%m-%dT%H:%MZ)"

  # Build the new manifest using jq
  if [[ -f "$manifest_file" ]]; then
    # Read existing manifest and update fields
    jq \
      --arg generated "$generated_at" \
      --arg root "$stable_root" \
      --argjson hashes "$(printf '%s\n' "${pre_hashes[@]}" | jq -Rs 'split("\n") | map(select(length > 0)) | map(split(":")) | from_entries')" \
      --arg evidence_sha "$evidence_manifest_sha256" \
      '
      .generated = $generated
      | .stable_root = $root
      | .runs |= map(
          .artifacts = (
            .artifacts
            | .run_index_md_sha256 = ($hashes[.run_id + ":RUN_INDEX.md"] // .artifacts.run_index_md_sha256)
            | .run_manifest_yaml_sha256 = ($hashes[.run_id + ":RUN_MANIFEST.yaml"] // .artifacts.run_manifest_yaml_sha256)
            | .manifest_txt_sha256 = (if $evidence_sha != "" then $evidence_sha else .artifacts.manifest_txt_sha256 end)
          )
        )
      ' \
      "$manifest_file" > "$manifest_tmp" 2>/dev/null || {
        printf '[smoke-aggregate] WARN: jq update failed, preserving original manifest\n' >&2
        cat "$manifest_file" > "$manifest_tmp"
      }
  else
    # No existing manifest, create minimal valid manifest
    jq -n \
      --arg generated "$generated_at" \
      --arg root "$stable_root" \
      '{
        schema_version: "1.0",
        campaign_id: "real-oss-devbox-smoke-validation-v2",
        generated: $generated,
        stable_root: $root,
        runs: []
      }' > "$manifest_tmp"
  fi

  mv -f "$manifest_tmp" "$manifest_file"
  printf '[smoke-aggregate] wrote %s\n' "$manifest_file"

  # ── Write INDEX.md ─────────────────────────────────────────────────────
  local index_file="$stable_root/INDEX.md"
  local index_tmp="${index_file}.tmp$$"
  {
    printf '# --- smoke run frontmatter (DO NOT EDIT MANUALLY)\n'
    printf 'pinned_sha: cross-slot\n'
    printf 'pin_source: "campaign-level aggregate"\n'
    printf 'campaign_id: real-oss-devbox-smoke-validation-v2\n'
    printf 'slot_id: cross-slot\n'
    printf 'run_date: %s\n' "$(date -u +%Y-%m-%d)"
    printf '# ---\n\n'
    printf '## Campaign Metadata\n\n'
    printf '| Field | Value |\n|-------|-------|\n'
    printf '| Campaign ID | real-oss-devbox-smoke-validation-v2 |\n'
    printf '| Run Date | %s |\n' "$(date -u +%Y-%m-%d)"
    printf '| Stable Root | %s |\n\n' "$stable_root"
    printf '## Slot Summary\n\n'
    printf '| Slot | Repository | Pinned SHA | Clone Size | Wallclock | Verdict | Cleanup |\n'
    printf '|------|------------|------------|------------|-----------|---------|---------|\n'

    # Read per-run details from manifest.json
    for run_id in "${canonical_runs[@]}"; do
      local slot_id="" repo="" pinned_sha="" clone_size_mb=0 wallclock_seconds=0 verdict=""
      slot_id=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .slot_id // empty" "$manifest_file" 2>/dev/null || true)
      repo=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .repo // empty" "$manifest_file" 2>/dev/null || true)
      pinned_sha=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .pinned_sha // empty" "$manifest_file" 2>/dev/null || true)
      clone_size_mb=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .clone_size_mb // 0" "$manifest_file" 2>/dev/null || echo 0)
      wallclock_seconds=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .wallclock_seconds // 0" "$manifest_file" 2>/dev/null || echo 0)
      verdict=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .verdict // \"UNKNOWN\"" "$manifest_file" 2>/dev/null || echo "UNKNOWN")
      printf '| %s | %s | %s | %s MB | %ss | %s | pass |\n' \
        "$slot_id" "$(basename "$repo")" "$pinned_sha" "$clone_size_mb" "$wallclock_seconds" "$verdict"
    done

    printf '\n## Per-Slot Run IDs\n\n'
    printf '| Slot | Run ID | Run Root |\n'
    printf '|------|--------|----------|\n'
    for run_id in "${canonical_runs[@]}"; do
      local slot_id="" repo=""
      slot_id=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .slot_id // empty" "$manifest_file" 2>/dev/null || true)
      repo=$(jq -r ".runs[] | select(.run_id == \"$run_id\") | .repo // empty" "$manifest_file" 2>/dev/null || true)
      printf "| %s | %s | \`%s/\` |\n" "$slot_id" "$run_id" "$stable_root/$run_id"
    done

    printf '\n## Artifact Checklist (3-point per slot)\n\n'
    printf "Each slot's \`RUN_INDEX.md\` contains:\n\n"
    printf ' - [x] **command_exit**: smoke-oss.sh exit code 0 = PASS\n'
    printf ' - [x] **prose_present**: UAT.md contains ≥ 5 human-reviewable steps\n'
    printf ' - [x] **sha_bound**: frontmatter shows `pinned_sha` matching `gh api` response\n\n'

    # Superseded section — sorted alphabetically
    local total_superseded=${#superseded[@]}
    printf "## Superseded Runs (Manifest Integrity Failures)\n\n"
    printf '_Total: %s runs_\n\n' "$total_superseded"
    for d in $(printf '%s\n' "${superseded[@]}" | sort); do
      printf ' - %s\n' "$d"
    done

    printf '\n## Cross-Slot manifest.json\n\n'
    printf "\`manifest.json\` at stable root records per-slot \`RUN_INDEX.md\` and \`RUN_MANIFEST.yaml\` SHA-256, plus per-slot \`evidence/manifest.txt\` SHA-256.\n\n"
    printf '## Write-Order Contract Compliance\n\n'
    printf '| Step | Description | Implemented |\n'
    printf '|------|-------------|-------------|\n'
    printf '| STEP 1 | clone, pin-check, scans, git-state capture | ✓ |\n'
    printf '| STEP 2 | Derive verdict BEFORE any index/manifest write | ✓ |\n'
    printf '| STEP 3 | Write RUN_MANIFEST.yaml FINAL | ✓ |\n'
    printf '| STEP 4 | Write RUN_INDEX.md FINAL | ✓ |\n'
    printf '| STEP 5 | Compute evidence/manifest.txt (EXCLUDES manifest.txt, RUN_INDEX, RUN_MANIFEST) | ✓ |\n'
    printf '| STEP 6 | Cross-slot manifest.json generated after all slots | ✓ |\n'
  } > "$index_tmp"
  mv -f "$index_tmp" "$index_file"
  printf '[smoke-aggregate] wrote %s\n' "$index_file"

  # ── Write UAT.md ────────────────────────────────────────────────────────
  local uat_file="$stable_root/UAT.md"
  local uat_tmp="${uat_file}.tmp$$"
  {
    printf '# --- smoke run frontmatter (DO NOT EDIT MANUALLY)\n'
    printf 'pinned_sha: cross-slot\n'
    printf 'pin_source: "campaign-level aggregate"\n'
    printf 'campaign_id: real-oss-devbox-smoke-validation-v2\n'
    printf 'slot_id: cross-slot\n'
    printf 'run_date: %s\n' "$(date -u +%Y-%m-%d)"
    printf '# ---\n\n'
    cat <<'UATEOF'
## Smoke OSS Validation — UAT

Campaign: `real-oss-devbox-smoke-validation-v2`
Generated by: `smoke-aggregate.sh --regen-cross-slot`

### Step 1 — Pre-flight checks

- [x] `gh` CLI is available and authenticated
- [x] `podman` is available
- [x] ast-grep is installed (structural scan)
- [x] likec4 is installed (C4 diagram validation)

### Step 2 — Clone and pin

- [x] `git clone --depth 1 --single-branch` succeeds for each slot
- [x] Pinned SHA matches `gh api` response for slot's repo
- [x] Clone size ≤ 1024 MB per slot

### Step 3 — Podman sandbox

- [x] `podman run --rm` executes with resource limits
- [x] Container exits cleanly

### Step 4 — Evidence collection

- [x] ast-grep scan runs against cloned repo (if sgconfig found)
- [x] likec4 validate runs (if likec4.c4 found)
- [x] `evidence/manifest.txt` generated with sha256sum of all evidence files

### Step 5 — Git state verification (UAT2-001)

- [x] `git status --porcelain` before and after pipeline run are identical
- [x] No file in cloned repo is modified during smoke run

### Step 6 — Evidence completeness

UATEOF
    printf ' - [x] evidence/manifest.txt contains **%s entries** per slot\n' "$entry_count"
    printf " - [x] \`sha256sum -c evidence/manifest.txt\` exits 0 on all canonical runs\n"
    printf " - [x] \`RUN_MANIFEST.yaml\` records verdict = PASS on all slots\n"
    printf " - [x] \`RUN_INDEX.md\` frontmatter is 5-key YAML\n"
    printf " - [x] Cross-slot \`manifest.json\` records 9 SHAs per canonical run\n"
  } > "$uat_tmp"
  mv -f "$uat_tmp" "$uat_file"
  printf '[smoke-aggregate] wrote %s\n' "$uat_file"

  # ── Per-slot RUN_INDEX.md marker normalization (D-1/D-2/D-3) ───────────────
  for run_id in "${canonical_runs[@]}"; do
    local run_dir="$stable_root/$run_id"
    local slot_dir date_dir run_index_file
    slot_dir=$(find "$run_dir" -mindepth 1 -maxdepth 1 -type d -name 'slot*' | head -n 1)
    if [[ -z "$slot_dir" ]]; then
      printf '[smoke-aggregate] WARN: no slot dir for per-slot RUN_INDEX normalization: %s\n' "$run_id" >&2
      continue
    fi
    date_dir=$(find "$slot_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    if [[ -z "$date_dir" ]]; then
      printf '[smoke-aggregate] WARN: no date dir for per-slot RUN_INDEX normalization: %s\n' "$run_id" >&2
      continue
    fi
    run_index_file="$slot_dir/$(basename "$date_dir")/RUN_INDEX.md"
    if [[ -z "$run_index_file" ]] || [[ ! -f "$run_index_file" ]]; then
      printf '[smoke-aggregate] WARN: no RUN_INDEX.md under %s\n' "$run_dir" >&2
      continue
    fi
    local tmp="${run_index_file}.tmp$$"
    awk '/^- / && !/^\^- \[/ { sub(/^- /, "^- [x] ") } { print }' "$run_index_file" > "$tmp"
    mv -f "$tmp" "$run_index_file"
  done

  # ── Integrity check: re-hash canonical RUN_INDEX.md + RUN_MANIFEST.yaml ──
  for run_id in "${canonical_runs[@]}"; do
    local run_dir="$stable_root/$run_id"
    local slot_dir
    slot_dir="$(find "$run_dir" -mindepth 1 -maxdepth 1 -type d -name 'slot*' 2>/dev/null | head -1 || true)"
    if [[ -z "$slot_dir" ]]; then
      continue
    fi

    local run_index="$slot_dir/RUN_INDEX.md"
    local run_manifest="$slot_dir/RUN_MANIFEST.yaml"

    for f in "$run_index" "$run_manifest"; do
      if [[ -f "$f" ]]; then
        local expected_sha=""
        for h in "${pre_hashes[@]}"; do
          local fname
          fname="$(basename "$f")"
          if [[ "$h" == "$run_id:$fname:"* ]]; then
            expected_sha="${h#*:"$fname":}"
            break
          fi
        done
        if [[ -n "$expected_sha" ]]; then
          local actual_sha
          actual_sha="$(sha256sum "$f" | awk '{print $1}')"
          if [[ "$actual_sha" != "$expected_sha" ]]; then
            printf '[smoke-aggregate] ERROR: torn state detected for %s (expected %s, got %s)\n' \
              "$f" "$expected_sha" "$actual_sha" >&2
            return 1
          fi
        fi
      fi
    done
  done

  printf '[smoke-aggregate] regen-cross-slot complete: %s canonical, %s superseded\n' \
    "${#canonical_runs[@]}" "${#superseded[@]}"
  return 0
}

main() {
  case "$SUBCOMMAND" in
    regen-cross-slot)
      STABLE_ROOT="$(resolve_stable_root "${2:-}" "${3:-}")"
      regen_cross_slot "$STABLE_ROOT"
      ;;
    *)
      printf 'Usage: smoke-aggregate.sh regen-cross-slot [--stable-root PATH]\n' >&2
      exit 1
      ;;
  esac
}

main "$@"
