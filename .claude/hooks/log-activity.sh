#!/usr/bin/env bash
# Append one line per tool call (PostToolUse) and per subagent start/stop to $CLAUDE_ACTIVITY_LOG:
#   HH:MM:SS [agent-type] CATEGORY target
# The [agent-type] prefix appears only for calls made inside a subagent. Categories: READ, SEARCH, EDIT, BASH, AGENT,
# WEB, TOOL. Does nothing when CLAUDE_ACTIVITY_LOG is unset; wire it from personal settings (.claude/settings.local.json).
set -u

[ -n "${CLAUDE_ACTIVITY_LOG:-}" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
root=${CLAUDE_PROJECT_DIR:-}

line=$(printf '%s' "$input" | jq -r --arg root "$root" '
  def short: if $root != "" and startswith($root + "/") then .[($root | length) + 1:] else . end;
  def flat: tostring | gsub("[\r\n\t]+"; " ") | .[0:160];
  (if (.agent_type // "") != "" then "[\(.agent_type)] " else "" end) as $who
  | if .hook_event_name == "SubagentStart" then "AGENT ▶ start \(.agent_type // "subagent")"
    elif .hook_event_name == "SubagentStop" then "AGENT ■ stop \(.agent_type // "subagent")"
    else
      (.tool_input // {}) as $in
      | (.tool_name // "") as $t
      | if $t == "Read" then "\($who)READ \($in.file_path | short)"
        elif $t == "Grep" then "\($who)SEARCH grep \($in.pattern | flat)\(if $in.path then " in " + ($in.path | short) else "" end)"
        elif $t == "Glob" then "\($who)SEARCH glob \($in.pattern | flat)"
        elif ($t == "Edit" or $t == "Write" or $t == "MultiEdit" or $t == "NotebookEdit") then "\($who)EDIT \(($in.file_path // $in.notebook_path) | short)"
        elif $t == "Bash" then "\($who)BASH \($in.command | flat)"
        elif ($t == "Agent" or $t == "Task") then "\($who)AGENT \($in.subagent_type // "agent"): \(($in.description // "") | flat)"
        elif ($t == "WebFetch" or $t == "WebSearch") then "\($who)WEB \(($in.url // $in.query // "") | flat)"
        else "\($who)TOOL \($t)" end
    end')
[ -n "$line" ] || exit 0
printf '%s %s\n' "$(date +%H:%M:%S)" "$line" >>"$CLAUDE_ACTIVITY_LOG"
exit 0
