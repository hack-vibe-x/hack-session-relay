#!/bin/sh
# Installs the session-relay skills for Claude Code (~/.claude/skills) and Codex (~/.agents/skills).
# Usage: sh install.sh [--server https://your-relay.up.railway.app]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ "$1" = "--server" ] && [ -n "$2" ]; then
  printf '{"server_url": "%s"}\n' "$2" > "$HERE/skills/session-relay/scripts/defaults.json"
fi
for dest in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  mkdir -p "$dest"
  for skill in session-relay session-relay-init; do
    rm -rf "$dest/$skill"
    cp -R "$HERE/skills/$skill" "$dest/$skill"
    rm -rf "$dest/$skill/scripts/__pycache__"
  done
  echo "installed: $dest/session-relay, $dest/session-relay-init"
done
echo "Next: in Claude Code or Codex, run session-relay-init and enter the code."
