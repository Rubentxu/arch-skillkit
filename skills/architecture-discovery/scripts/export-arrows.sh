#!/usr/bin/env bash
# Arrows projections (M5, pipeline step 10 of docs/07 workflow).
# Derives exploratory graph views from the evidence bundle — never from
# invention. Views are generated ONLY when their evidence exists; every
# node/relationship keeps provenance so the Review role can audit
# consistency with LikeC4 (docs/12: Arrows may be more detailed than the
# model, but must never contradict it).
#
# Schema (OQ-05): arch-skillkit/arrows-v1 — a property graph of
# {schema, source, title, nodes: [{id, labels, properties}],
#  relationships: [{id, type, start, end, properties}]}.
# Rendering/import into arrows.app is a deferred adapter (ADR-0006: the
# projection layer is replaceable).
#
# Usage: export-arrows.sh [--repo <path>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: export-arrows.sh [--repo <path>]

Derives .arrows graph views from the evidence bundle into the project
workspace arrows/ directory:
  overview.arrows      always (project + build systems)
  dependencies.arrows  cargo metadata / package.json present
  endpoints.arrows     endpoint pattern matches present
  messaging.arrows     messaging pattern matches present
  data-access.arrows   persistence pattern matches present
EOF
}

repo_arg=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || { printf 'error: --repo needs a value\n' >&2; exit 2; }
      repo_arg="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'error: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_tools git jq

root="$(repo_root "$repo_arg")" || {
  printf 'error: %s is not inside a git work tree\n' "${repo_arg:-$PWD}" >&2
  exit 1
}
pid="$(registry_find_by_root "$root")"
if [ -z "$pid" ]; then
  printf 'error: repository %s is not registered yet; run workspace.sh first\n' "$root" >&2
  exit 1
fi
workspace="$(registry_get_field "$pid" workspace)"
project_name="$(jq -r --arg root "$root" '.projects[] | select(.root == $root) | .project_id' "$(arch_registry_file)")"
commit="$(git -C "$root" rev-parse HEAD)"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
evidence="$workspace/evidence/raw"
out="$workspace/arrows"
mkdir -p "$out"

# Common envelope; reads the graph body from stdin as {nodes, relationships}.
wrap() { # $1: title, $2: output file
  jq -s \
    --arg schema "arch-skillkit/arrows-v1" \
    --arg generated_by "export-arrows.sh" \
    --arg title "$1" \
    --arg project_id "$pid" \
    --arg commit "$commit" \
    --arg now "$now" \
    '.[0] + {
      schema: $schema,
      generated_by: $generated_by,
      title: $title,
      source: {project_id: $project_id, commit: $commit, generated_at: $now}
    }' >"$2"
}

# Self-check: every relationship endpoint must reference an existing node.
assert_integrity() { # $1: file
  local bad
  bad="$(jq -r '([.nodes[].id] | sort) as $ids
    | .relationships[]
    | select((.start as $s | $ids | index($s) | not) or (.end as $e | $ids | index($e) | not))
    | .id' "$1")"
  if [ -n "$bad" ]; then
    printf 'error: broken relationships in %s: %s\n' "$1" "$bad" >&2
    exit 1
  fi
}

# --- overview.arrows (always) --------------------------------------------
overview_body="$(
  jq -n --arg name "$project_name" --arg commit "$commit" '{
    nodes: [{id: "project", labels: ["Project"], properties: {name: $name, commit: $commit}}],
    relationships: []
  }'
)"
if [ -f "$evidence/build/build.provenance.json" ]; then
  overview_body="$(jq -n --argjson base "$overview_body" --slurpfile prov "$evidence/build/build.provenance.json" '
    $base
    | .nodes += [$prov[0].systems[] | {
        id: ("build:" + .system),
        labels: ["BuildSystem"],
        properties: {system: .system, status: .status}
      }]
    | .relationships += [$prov[0].systems[] | {
        id: ("rel:build:" + .system),
        type: "USES_BUILD_SYSTEM",
        start: "project",
        end: ("build:" + .system),
        properties: {}
      }]
  ')"
fi
printf '%s' "$overview_body" | wrap "Overview" "$out/overview.arrows"
assert_integrity "$out/overview.arrows"

# --- dependencies.arrows (build manifests present) ------------------------
dep_bodies=()
if [ -f "$evidence/build/cargo-metadata.json" ]; then
  dep_bodies+=("$(jq '
    (.workspace_members) as $ws
    | {
      nodes: [.packages[] | . as $p | {
        id: ("crate:" + .name),
        labels: (if ($ws | any(. == $p.id)) then ["Crate"] else ["ExternalCrate"] end),
        properties: {name: .name, version: .version}
      }],
      relationships: [.packages[] | . as $p | .dependencies[]? | {
        id: ("rel:dep:" + $p.name + ":" + .name),
        type: "DEPENDS_ON",
        start: ("crate:" + $p.name),
        end: ("crate:" + .name),
        properties: {}
      }]
    }' "$evidence/build/cargo-metadata.json")")
fi
if [ -f "$evidence/build/npm-package.json" ]; then
  dep_bodies+=("$(jq --arg name "$project_name" '{
    nodes: ([{id: "project", labels: ["Project"], properties: {name: $name}}]
      + [(.dependencies // {} | to_entries[]) | {
          id: ("dep:npm:" + .key),
          labels: ["ExternalDependency"],
          properties: {name: .key, version: .value}
        }]),
    relationships: [(.dependencies // {} | to_entries[]) | {
      id: ("rel:dep:npm:" + .key),
      type: "DEPENDS_ON",
      start: "project",
      end: ("dep:npm:" + .key),
      properties: {}
    }]
  }' "$evidence/build/npm-package.json")")
fi
if [ "${#dep_bodies[@]}" -gt 0 ]; then
  printf '%s\n' "${dep_bodies[@]}" | jq -s '{nodes: (map(.nodes) | add), relationships: (map(.relationships) | add)}' |
    wrap "Dependencies" "$out/dependencies.arrows"
  assert_integrity "$out/dependencies.arrows"
fi

# --- pattern-derived views (only when matches exist) ----------------------
pattern_view() { # $1: output file, $2: title, $3: rule substring, $4: node label, $5: message substring
  local f="$out/$1" body
  body="$(jq --arg root "$root" --arg pat "$3" --arg label "$4" --arg message "$5" '
    [.results[] | select(
      (((.check_id? // "") | tostring) | contains($pat))
      or ((((.extra? // {}).message? // "") | tostring) | contains($message))
    )] as $rs
    | if ($rs | length) == 0 then empty else
    {
      nodes: (
        [$rs[] | ((.path | sub("^" + $root + "/"; ""))) as $f | {
          id: ("node:" + $f + ":" + (.start.line | tostring)),
          labels: [$label],
          properties: {rule: .check_id, location: ($f + ":" + (.start.line | tostring))}
        }]
        + [$rs[] | ((.path | sub("^" + $root + "/"; ""))) as $f | {
            id: ("file:" + $f), labels: ["SourceFile"], properties: {path: $f}
          }]
        | unique_by(.id)
      ),
      relationships: [$rs[] | ((.path | sub("^" + $root + "/"; ""))) as $f | {
        id: ("rel:" + $f + ":" + (.start.line | tostring)),
        type: "DECLARED_IN",
        start: ("node:" + $f + ":" + (.start.line | tostring)),
        end: ("file:" + $f),
        properties: {}
      }]
    } end' "$evidence/semgrep.json" 2>/dev/null)" || body=""
  [ -n "$body" ] || return 0
  printf '%s' "$body" | wrap "$2" "$f"
  assert_integrity "$f"
  printf 'arrows: %s (%s)\n' "$1" "$4"
}

if [ -f "$evidence/semgrep.json" ]; then
  pattern_view "endpoints.arrows" "Endpoints" ".endpoint" "Endpoint" "HTTP endpoint"
  pattern_view "messaging.arrows" "Messaging" "messaging" "MessagingConsumer" "messaging consumer"
  pattern_view "data-access.arrows" "Data access" "persistence" "DataAccess" "persistence port"
fi

printf 'export-arrows: done\noutput: %s\n' "$out"
