#!/usr/bin/env bash
# LikeC4 model validation (M4.1, pipeline Fase/step 12 of docs/07 workflow).
# Validates the project model with the pinned likec4 CLI. Read-only: it
# never modifies the model. On failure it prints the parser errors and exits
# non-zero — the last valid model is retained (docs/23).
#
# Usage: model-validate.sh [--repo <path>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: model-validate.sh [--repo <path>]

Validates likec4/*.c4 in the project workspace with the pinned likec4 CLI.
A workspace without a model is a no-op (nothing to validate yet).
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

require_tools git jq mise

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
model_dir="$workspace/likec4"

if ! find "$model_dir" -maxdepth 1 -name '*.c4' -type f 2>/dev/null | grep -q .; then
  printf 'no model to validate (likec4/ has no .c4 files yet)\n'
  exit 0
fi

skill_dir="$(cd "$SCRIPT_DIR/.." && pwd)"
runtime_dir="$skill_dir/runtime"

rc=0
arch_mise "$runtime_dir" likec4 validate "$model_dir" || rc=$?
if [ "$rc" -ne 0 ]; then
  printf 'error: LikeC4 model is invalid; the last valid model is retained — fix the errors above\n' >&2
fi
exit "$rc"
