---
name: session-relay
description: Sends this computer's Claude Code and Codex conversation records to the session-relay server once a day, with a code the admin issued. Shows the sync status, syncs now, or stops it. Setting it up with a code is the session-relay-init skill. Use for "session-relay status", "session relay", "세션 릴레이 상태", "동기화 상태", "지금 동기화해줘", "세션 전송 멈춰줘", "session-relay sync", "session-relay stop".
---

# session-relay

Once set up with `session-relay-init`, a background job on this computer sends the Claude Code and Codex
conversation records to the relay server: at login and then once a day. Each session is cut into one file per
date, so a session used across midnight lands in both dates, and a slice is sent again only when it changed.
When the code's end time passes, or the server says it ended, the job removes itself and stops calling the server.

`<skill>` below is the absolute path of this skill folder. Everything this computer keeps is in `~/.session-relay/`.
Script output is in English; tell the person what it says in the language they use with you.

## Status
```bash
python3 <skill>/scripts/relay.py status
```
Tell them: the user it is set up for, the end time, whether the daily job is on, the last sync and how much it
sent, and any errors. If it says "syncing now", the upload is still running in the background.

## Sync now
Only when the person asks. It runs in the foreground and can take a while the first time.
```bash
python3 <skill>/scripts/relay.py sync
```

## Stop
Only when the person asks. Confirm first: this computer stops sending and calling the server, and it starts
again only with `session-relay-init` and a valid code.
```bash
python3 <skill>/scripts/relay.py stop
```

## What is sent
- Claude Code: `~/.claude/projects/<project>/<session>.jsonl` (subagent records are not sent).
- Codex: `~/.codex/sessions/**/rollout-*.jsonl` and `~/.codex/archived_sessions/`. Sessions Codex imported from
  Claude Code are not sent again.
- Left out: runs started by a program (`claude -p`, `codex exec`, Codex subagents) and internal request dumps
  inside a session (`api-request*`, `file-history-snapshot` lines).

## Do not
- Run `stop` or `sync` unasked.
- Show the code in full to anyone but the person; it is in `~/.session-relay/config.json`.
