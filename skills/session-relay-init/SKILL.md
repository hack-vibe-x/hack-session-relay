---
name: session-relay-init
description: Sets up session-relay on this computer with the code the admin gave. Asks for the code, checks it with the server, saves it, registers a daily job and starts the first upload of every Claude Code and Codex conversation on this computer. Use for "session-relay-init", "session relay init", "세션 릴레이 시작", "세션 릴레이 설정", "코드 입력할게", "릴레이 코드 등록".
---

# session-relay-init

The scripts are in the sibling skill: `<skills>/session-relay/scripts/relay.py`, where `<skills>` is the folder
that holds this skill folder. Script output is in English; tell the person what it says in their language.

## 1. Ask for the code
Ask in one message, and say what happens once it is entered:
- Every Claude Code and Codex conversation on this computer is sent to the relay server now, then once a day
  (at login, if the day has not been sent yet) until the code's end date.
- After the end date it stops by itself.

The code looks like `SR-XXXX-XXXX-XXXX-XXXX` (dashes and case do not matter). Wait for the person's answer.
If they also got a server address (https://...), take it too.

## 2. Check and set up
```bash
python3 <skills>/session-relay/scripts/relay.py init --code "<code>"
```
Add `--server <url>` only when the person gave one, or when the result says there is no server address (then ask
for it).

- "This code is not valid": ask them to check the code. Do not guess or retry other codes.
- "already ended": tell them to ask the admin for a new code.
- "Could not reach the server": pass the error on; try again only if they ask.
- Success: tell them which user it is set up for, the end date, how many session files were found, and that the
  first upload runs in the background. They can check it with the session-relay skill ("session-relay status").

On a computer other than macOS the daily job is not registered; the script uploads in the foreground. Tell them
to run `relay.py tick` once a day themselves for now.

## Do not
- Run init without a code the person typed.
- Paste the code into files, commits or memory.
