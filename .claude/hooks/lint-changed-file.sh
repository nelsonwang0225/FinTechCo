#!/usr/bin/env bash
# PostToolUse (Edit|Write|MultiEdit): lint the one file that was just changed.
#   backend/**/*.py         -> ruff (config in backend/pyproject.toml)
#   frontend/src/**/*.ts(x) -> eslint (config in frontend/eslint.config.js)
#   anything else           -> exit 0, no output
# Pass: prints {"systemMessage": "✓ Lint passed: ..."} so the result shows in the transcript.
# Fail: prints the linter's own output on stderr and exits 2, which hands it to Claude to fix.
# If CLAUDE_ACTIVITY_LOG is set, a LINT line is appended to it as well.
set -u

command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
agent=$(printf '%s' "$input" | jq -r '.agent_type // empty')
[ -n "$file" ] || exit 0

root=${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
case "$file" in
  /*) abs=$file ;;
  *) abs="$root/$file" ;;
esac
rel=${abs#"$root"/}
[ "$rel" != "$abs" ] || exit 0   # outside this repository
[ -f "$abs" ] || exit 0

case "$rel" in
  backend/*.py)
    tool=ruff
    cmd=("$root/backend/.venv/bin/ruff" check --no-cache "$abs")
    workdir="$root/backend"
    ;;
  frontend/src/*.ts | frontend/src/*.tsx)
    tool=eslint
    cmd=("$root/frontend/node_modules/.bin/eslint" "$abs")
    workdir="$root/frontend"
    ;;
  *) exit 0 ;;
esac
[ -x "${cmd[0]}" ] || exit 0   # linter not installed yet (run make setup)

now() { perl -MTime::HiRes=time -e 'printf "%.3f", time'; }
log() {
  [ -n "${CLAUDE_ACTIVITY_LOG:-}" ] || return 0
  printf '%s %s%s\n' "$(date +%H:%M:%S)" "${agent:+[$agent] }" "$1" >>"$CLAUDE_ACTIVITY_LOG"
}

start=$(now)
output=$(cd "$workdir" && "${cmd[@]}" 2>&1)
status=$?
secs=$(perl -e "printf '%.1f', $(now) - $start")

if [ "$status" -eq 0 ]; then
  log "LINT ✓ $rel ($tool, ${secs}s)"
  jq -cn --arg m "✓ Lint passed: $rel ($tool, ${secs}s)" '{systemMessage: $m}'
  exit 0
fi

log "LINT ✗ $rel ($tool, ${secs}s)"
jq -cn --arg m "✗ Lint failed: $rel ($tool, ${secs}s)" '{systemMessage: $m}'
printf '%s failed for %s:\n%s\n' "$tool" "$rel" "$output" >&2
exit 2
