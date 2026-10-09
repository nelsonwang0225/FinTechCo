#!/usr/bin/env bash
# Live, colour-coded view of the Claude Code activity log.
# Usage: .claude/hooks/watch-activity.sh [log-file]   (default: $CLAUDE_ACTIVITY_LOG, then ~/claude-audit.log)
set -u

log=${1:-${CLAUDE_ACTIVITY_LOG:-$HOME/claude-audit.log}}
touch "$log"

esc=$'\033'
reset="${esc}[0m"; dim="${esc}[2m"; bold="${esc}[1m"
blue="${esc}[34m"; cyan="${esc}[36m"; yellow="${esc}[33m"; magenta="${esc}[35m"
green="${esc}[32m"; red="${esc}[31m"; white="${esc}[37m"

printf '%s%s Claude Code activity %s %s%s\n' "$bold" "$white" "$dim" "$log" "$reset"
printf '%sREAD%s  %sSEARCH%s  %sEDIT%s  %sBASH%s  %sAGENT%s  %sLINT/TEST ✓%s  %s✗%s\n' \
  "$blue" "$reset" "$cyan" "$reset" "$yellow" "$reset" "$white" "$reset" "$magenta" "$reset" "$green" "$reset" "$red" "$reset"
printf '%s%s%s\n' "$dim" "────────────────────────────────────────────────────────────" "$reset"

tail -n 20 -F "$log" 2>/dev/null | while IFS= read -r raw; do
  time=${raw%% *}
  rest=${raw#* }
  who=""
  case "$rest" in
    "["*"] "*) who=${rest%%] *}]; rest=${rest#*] } ;;
  esac
  cat=${rest%% *}
  case "$cat" in
    READ) color=$blue ;;
    SEARCH) color=$cyan ;;
    EDIT) color=$yellow ;;
    BASH) color=$white ;;
    AGENT) color=$magenta ;;
    LINT | TEST) case "$rest" in *"✗"*) color=$red ;; *) color=$green ;; esac ;;
    *) color=$dim ;;
  esac
  printf '%s%s%s %s%s%s%s%-6s%s %s\n' "$dim" "$time" "$reset" "$magenta" "${who:+$who }" "$reset" "$bold$color" "$cat" "$reset" "${color}${rest#"$cat" }${reset}"
done
