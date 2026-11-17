#!/bin/sh
# session-relay installer: one line, from a terminal or run by an AI agent.
#
#   curl -fsSL https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/main/install.sh | sh -s SR-XXXX-XXXX-XXXX-XXXX
#   sh install.sh --code SR-XXXX-XXXX-XXXX-XXXX        (from a clone of the repository)
#
# Without a code it asks for one when a terminal is attached; an AI agent must pass --code.
# Other options go to `relay init`: --server URL, --no-job, --no-skill, --foreground.
# Installs into ~/.session-relay. Remove with: ~/.session-relay/relay uninstall
set -eu

REPO="${SESSION_RELAY_REPO:-hack-vibe-x/hack-session-relay}"
REF="${SESSION_RELAY_REF:-main}"
FILES="client/relay.py client/sources.py client/media.py client/redact.py client/defaults.json skill/SKILL.md"

is_ko() {
  case "${SESSION_RELAY_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in ko*|KO*) return 0 ;; esac
  return 1
}
say() { if is_ko; then printf '[session-relay] %s\n' "$1"; else printf '[session-relay] %s\n' "$2"; fi; }

CODE=""
PASS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --code) CODE="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --code=*) CODE="${1#--code=}"; shift ;;
    SR-*|sr-*) CODE="$1"; shift ;;
    # A chat app may turn the "--" in the copied one-liner into a dash; skip it.
    --|—|–|―) shift ;;
    *) PASS="$PASS $1"; shift ;;
  esac
done

PY="$(command -v python3 || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
  say "python3(3.9 이상)이 필요합니다. macOS라면 터미널에서 'xcode-select --install'로 개발자 도구를 설치한 뒤 이 명령을 다시 실행하세요." \
      "python3 (3.9+) is required. On macOS run 'xcode-select --install', then run this again."
  exit 1
fi

# From a clone: use its files. Piped from curl: download them.
SRC=""
TMP=""
case "$0" in
  *install.sh)
    HERE="$(cd "$(dirname "$0")" && pwd)"
    [ -f "$HERE/client/relay.py" ] && SRC="$HERE" ;;
esac
cleanup() { if [ -n "$TMP" ]; then rm -rf "$TMP"; fi; return 0; }
trap cleanup EXIT INT TERM
if [ -z "$SRC" ]; then
  TMP="$(mktemp -d)"
  for f in $FILES; do
    mkdir -p "$TMP/$(dirname "$f")"
    if ! curl -fsSL "https://raw.githubusercontent.com/$REPO/$REF/$f" -o "$TMP/$f"; then
      say "설치 파일을 받지 못했습니다 ($f). 인터넷 연결을 확인하고 다시 실행하세요." \
          "Could not download $f. Check the connection and run this again."
      exit 1
    fi
  done
  SRC="$TMP"
fi

if [ -z "$CODE" ] && (exec </dev/tty) 2>/dev/null; then
  if is_ko; then printf '접속 코드를 입력하세요 (SR-XXXX-XXXX-XXXX-XXXX): ' >/dev/tty
  else printf 'Enter your code (SR-XXXX-XXXX-XXXX-XXXX): ' >/dev/tty; fi
  read -r CODE </dev/tty || CODE=""
fi
if [ -z "$CODE" ]; then
  say "접속 코드가 필요합니다. 예: sh install.sh --code SR-XXXX-XXXX-XXXX-XXXX" \
      "A code is required, e.g. sh install.sh --code SR-XXXX-XXXX-XXXX-XXXX"
  exit 2
fi

# $PASS is split on spaces on purpose: options and URLs have none.
set +e
# shellcheck disable=SC2086
"$PY" "$SRC/client/relay.py" init --code "$CODE" $PASS
STATUS=$?
cleanup
trap - EXIT INT TERM
exit "$STATUS"
