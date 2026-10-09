#!/usr/bin/env bash
# PostToolUse (Bash): when the command ran pytest or vitest, show one summary line parsed from its real output,
# e.g. "✓ Tests: pytest 14 passed (test_payments_list_and_detail.py)". Any other command: exit 0, no output.
# Never blocks and never changes the tool result. If CLAUDE_ACTIVITY_LOG is set, a TEST line is appended too.
set -u

command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
case "$cmd" in
  *pytest* | *vitest* | *"make test"* | *"npm test"* | *"npm run test"*) ;;
  *) exit 0 ;;
esac
agent=$(printf '%s' "$input" | jq -r '.agent_type // empty')
out=$(printf '%s' "$input" | jq -r '[.tool_response.stdout?, .tool_response.stderr?, (.tool_response | strings)] | map(select(. != null)) | join("\n")' |
  sed -e $'s/\x1b\\[[0-9;]*m//g')

parts=()
failed=0
# pytest: the final "N passed, M failed ... in Xs" line (with or without the ==== frame).
py=$(printf '%s\n' "$out" | grep -E '^(=+ )?[0-9]+ (passed|failed|error|errors|skipped|deselected)[^=]* in [0-9.]+s' | tail -1 |
  sed -E 's/^=+ //; s/ =+$//; s/ in [0-9.]+s.*$//')
if [ -n "$py" ]; then
  parts+=("pytest $py")
  printf '%s' "$py" | grep -qE '[0-9]+ (failed|error)' && failed=1
fi
# vitest: the "Tests  N passed (N)" summary line.
vt=$(printf '%s\n' "$out" | grep -E '^ *Tests +[0-9]+' | tail -1 | sed -E 's/^ *Tests +//; s/ *\([0-9]+\)$//')
if [ -n "$vt" ]; then
  parts+=("vitest $vt")
  printf '%s' "$vt" | grep -qE '[0-9]+ failed' && failed=1
fi
[ ${#parts[@]} -gt 0 ] || exit 0

# What was targeted: test files named in the command, else the -k / K= / F= filter.
target=$(printf '%s\n' "$cmd" | grep -oE '[A-Za-z0-9_./-]*(test_[A-Za-z0-9_]+\.py|\.test\.tsx?)' | xargs -n1 basename 2>/dev/null | sort -u | paste -sd, -)
[ -n "$target" ] || target=$(printf '%s\n' "$cmd" | grep -oE '(-k|K=|F=) *"?[^" ]+' | head -1 | sed -E 's/^(-k|K=|F=) *"?//')
[ -n "$target" ] || case "$cmd" in *"make test-isolation"*) target="isolation" ;; esac
summary=$(IFS='; '; printf '%s' "${parts[*]}")
mark="✓"; [ "$failed" -eq 1 ] && mark="✗"
line="$mark Tests: $summary${target:+ ($target)}"

if [ -n "${CLAUDE_ACTIVITY_LOG:-}" ]; then
  printf '%s %s%s\n' "$(date +%H:%M:%S)" "${agent:+[$agent] }" "TEST $mark $summary${target:+ ($target)}" >>"$CLAUDE_ACTIVITY_LOG"
fi
jq -cn --arg m "$line" '{systemMessage: $m}'
exit 0
