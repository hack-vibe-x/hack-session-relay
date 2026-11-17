---
name: session-relay
description: Checks and controls session-relay on this computer, which sends the Claude Code and Codex conversation records to the relay server once a day. Shows the status, syncs now, changes the code, stops it or removes it. Use for "session relay status", "세션 릴레이 상태 알려줘", "동기화 상태", "지금 동기화해줘", "세션 전송 멈춰줘", "새 코드로 바꿔줘", "세션 릴레이 지워줘".
---

# session-relay

session-relay was installed on this computer with `install.sh` and a code from the admin. A background job sends
the Claude Code and Codex conversation records to the relay server at login and then once a day, until the code's
end date, when it stops by itself. Everything is in `~/.session-relay/`; the command is `~/.session-relay/relay`.
Its messages follow the locale (Korean or English); pass them on in the language the person uses with you.

| The person asks | Run |
|---|---|
| status, did it send, errors | `~/.session-relay/relay status` |
| send now | `~/.session-relay/relay sync` (foreground; the first one can take minutes) |
| use a new code / start again after stop | `~/.session-relay/relay init --code <code they typed>` |
| stop sending | `~/.session-relay/relay stop` |
| remove it | `~/.session-relay/relay uninstall` |

If `~/.session-relay/relay` does not exist, it is not installed: see https://github.com/hack-vibe-x/hack-session-relay.

## Do not
- Run `stop`, `uninstall` or `sync` unasked. Confirm `stop` and `uninstall` first: sending ends on this computer
  until it is set up again with a valid code.
- Invent or retry codes; use only a code the person typed.
- Show the code from `~/.session-relay/config.json` to anyone but the person.
