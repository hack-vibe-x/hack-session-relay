# session-relay

[English](#english) · [한국어](#한국어)

<a id="english"></a>

Collects Claude Code and Codex conversation records on a server, once a day. The user installs it once with an **access code** from the admin. After that there is nothing to do.

## For AI agents: installing this for the user

When a user asks you (Claude Code, Codex or another agent) to install this repository:

1. Tell the user, in their language, what installing does, then ask for their **access code** (it looks like `SR-XXXX-XXXX-XXXX-XXXX` and comes from the admin). Say this:
   - Every Claude Code and Codex conversation on this computer is sent to the session-relay server now, then once a day, until the code's end date.
   - API keys, tokens, passwords and other secrets, and personal information such as email addresses and phone numbers, are masked on this computer before anything is sent.
   - After the end date it stops by itself.

   If the user already pasted a message containing the code, use that code and do not ask again.
2. Run this (no clone needed; it does not wait for input when a code is given):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/main/install.sh | sh -s <CODE>
   ```
   From a clone, `sh install.sh --code <CODE>` does the same.
3. Pass the result on to the user.
   - **Success:** which user it is set up for, the end date, how many session files were found, and that the first upload runs in the background.
   - **"not valid":** ask the user to check the code. Never guess codes.
   - **"already ended":** the user needs a new code from the admin.
   - **python3 missing:** on macOS, `xcode-select --install`, then run it again.
4. Later requests ("status", "sync now", "stop", "new code") go to `~/.session-relay/relay status | sync | stop | init --code <CODE> | uninstall`. `~/.session-relay/README.md` lists them.

## Installing (users)

When the admin issues a code, the admin page writes the message below for the user. Pick either way.

**1) Let Claude Code or Codex do it**: paste the message and say "install this". Giving only this repository's address also works; the agent asks for the code.

**2) One line in a terminal**
```bash
curl -fsSL https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/main/install.sh | sh -s SR-XXXX-XXXX-XXXX-XXXX
```
Run without a code, it asks for one in the terminal.

Installing does the following, in this order:
1. Checks the code with the server. A wrong or ended code installs nothing.
2. Copies the program into `~/.session-relay/`.
3. Registers the daily job. It uses launchd on the Mac and wakes at login and every hour, but calls the server only once a day.
4. Installs the `session-relay` skill for Claude Code and Codex, so a chat can answer "session relay status". `--no-skill` leaves it out.
5. Starts the first upload in the background.

### After installing

| To | Terminal | In Claude or Codex |
|---|---|---|
| See the status | `~/.session-relay/relay status` | "session relay status" |
| Send now | `~/.session-relay/relay sync` | "sync now" |
| Stop | `~/.session-relay/relay stop` | "stop sending sessions" |
| Change the code / start again | `~/.session-relay/relay init --code SR-…` | "switch to the new code: SR-…" |
| Remove | `~/.session-relay/relay uninstall` | "remove session relay" |
| The end date has passed | It stops by itself | — |

Messages are in Korean when the system language is Korean, otherwise in English.

## How it works

- **Once a day, in this order**: the job wakes at login and every hour.
  1. If today was already sent, or the code's end date has passed, it ends without calling the server.
  2. It asks the server whether the code is still valid.
  3. If the server offers a newer client, it updates first (see [Updates](#updates)).
  4. It sends what is new.
  5. It records the day as sent in `~/.session-relay/state.json` and reports to the server (the admin page shows the last sync and the client version). The day counts as sent only when the run finished, so a failed run is retried the next hour.

  Days when the computer was off are sent at the next login.
- **Sessions across midnight**: every line is filed under the local date of its own time. A session used from the night of the 17th into the early 18th lands in both the 17th and the 18th folders.
- **No duplicates**: the sha256 of every (session, date) slice is kept in `~/.session-relay/state.json`, and only changed slices are sent again. The server overwrites the same slice. "Today" sent in the morning is replaced the next day by the full day.
- **Ending**: once the stored end time has passed, it stops without calling the server. It also stops when the server says the code has ended or is unknown. Stopping removes the launchd job too.
- **Secrets and personal information are masked before sending**: see [Sensitive information](#sensitive-information) below.
- **Images become text**: images and other base64 attachments (screenshots, PDFs) are replaced on the user's computer with a note such as `[image omitted: image/png, 245 KB]`, so they are never uploaded. On one machine this cut the compressed upload by about 80%. The server does the same for uploads from older clients and for files stored before.
- **Resend on request**: when the server's copy is lost, the admin can raise the user's epoch (`PATCH /admin/users/<id> {"resend": true}`), and the computer sends everything again at its next sync.
- **Not sent**: subagent records, sessions run by `claude -p` and `codex exec`, copies Codex imported from Claude Code, and the `api-request*` and `file-history-snapshot` lines inside a session.
- **Platforms**: the daily job is registered automatically on macOS only. The client uses only the Python standard library and runs on the python3 that ships with macOS (3.9).

### Updates

Installed computers update themselves; nobody has to reinstall.

- The admin releases a version with `scripts/release.py` (see [Releasing a client update](#releasing-a-client-update)). Until then, pushing to GitHub changes nothing on installed computers.
- At its daily check the computer sees the released version in the server's answer. If it is newer, it downloads that commit's files from this GitHub repository and checks each against the sha256 the server gave. It then runs the new code once as a test, swaps it in (the previous version stays in `~/.session-relay/app.prev`), and syncs with the new code.
- Files must come from this repository at the named commit and match the server's hashes, so neither GitHub nor the server alone can change the code that runs on users' computers.
- If anything fails (download, hash, test run), it keeps the current version, logs why, syncs as usual, and tries again the next day.
- Computers installed before 0.6.0 have no updater and need one manual reinstall.

### Sensitive information

Session records hold more than what was typed in the chat. They also hold the output of every command the agent ran and every file it read, so a `.env` file, a `cat ~/.aws/credentials` or a pasted key ends up in them. **session-relay masks these on the user's computer, before sending.** The server and the admin never receive the original values. Each one becomes a short note such as `[redacted: github token]`.

What is masked:

- API keys and tokens in known formats: Anthropic and OpenAI (`sk-…`), GitHub, GitLab, AWS, Google, Slack, Stripe, Hugging Face, npm, SendGrid, JWTs, and session-relay access codes
- Private keys (`-----BEGIN … PRIVATE KEY-----` blocks)
- Passwords in URLs (`postgres://user:password@host`) and `Authorization: Bearer|Basic` values
- Values assigned to secret-looking names, such as `API_KEY=…`, `DB_PASSWORD: …`, `"client_secret": "…"` and `auth_token=…`, in `.env` files, configs, code and commands
- Email addresses: the part before `@` is masked and the domain kept (`[redacted: email]@gmail.com`), so it still shows which organisation was involved. `noreply`, `git@github.com` and `example.com` addresses are left as they are.
- Phone numbers: Korean ones (`010-1234-5678`, `01012345678`, `+82 10-…`, `02-123-4567`) and international ones written with `+` (`+1 415 555 1234`)
- Resident registration numbers (`900101-1234567`, with the dash) and card numbers (16 digits, or 15 for Amex, that pass the card checksum)

Masking works by pattern (`client/redact.py`). A secret in an unusual format that matches none of the patterns can still get through. Names, postal addresses and company or customer names have no fixed form and are not masked; neither are customers' source code or documents that an agent read. When the patterns are updated, each computer reads its sessions again at the next sync and sends the slices that changed, so the copies on the server are replaced with the newly masked ones.

## Admin

| Folder | What | Where |
|---|---|---|
| `client/`, `install.sh`, `skill/` | What gets installed on the user's computer | User's Mac |
| `server/` | Issues and checks codes, stores records, zip downloads | Railway |
| `admin/` | Page to issue and end codes and download by date | Admin's Mac (127.0.0.1) |

### Server (Railway)

**Deployed at:** `https://session-relay-production.up.railway.app`
- Data is kept on the volume at `/data`.
- The server address is also in `client/defaults.json`.

To redeploy after changing the code, run `cd server && railway up`. On Railway the server refuses to start unless `/data` is a mounted volume, so it never writes records to the container's temporary disk. The first deployment did exactly that and lost everything on the next deploy. To set it up from scratch:

```bash
cd server
railway init --name session-relay
railway add --service session-relay --variables "ADMIN_KEY=$(openssl rand -hex 24)"
railway volume add --mount-path /data     # wait until it is attached before `railway up`
railway up
railway domain
```

### Releasing a client update

1. Raise `VERSION` in `client/relay.py`, run the tests, commit and push to `main`.
2. Check, then release:
   ```bash
   python3 scripts/release.py --dry-run
   python3 scripts/release.py
   ```
   It refuses when `client/` or `skill/` has uncommitted changes, when the commit is not on GitHub, when GitHub serves different files, or when the version is not newer than the released one.
3. Computers update at their next daily sync. The admin page shows the released version at the top and each user's client version, with a "waiting" badge until that user has updated.

### Admin page

```bash
cp admin/config.example.json admin/config.json   # fill in server_url and admin_key
python3 admin/admin.py                            # http://127.0.0.1:8787
```

- **Issue a code**: enter a phone number, a memo and an end date to get the code and the message for the user. The message can be copied again later from the user's page. The code itself is kept only in `admin/data/codes.json`; the server keeps only its hash.
- **Change the end date / End now**: the user's computer learns it at its next sync and stops by itself.
- **Client version**: each user's page shows the client version that computer runs.
- **Records**: switch between a calendar and a list. Click a date to see its sessions and a download button, or pick a range to download it all at once. The zip holds `<phone>/<date>/<tool>_<session id>.jsonl` and an `_index.json` per date.

## Tests

```bash
python3 tests/test_e2e.py
python3 tests/test_redact.py
python3 tests/test_media.py
```

- `test_redact.py` checks which secrets are masked and that ordinary code and prose are left alone.
- `test_media.py` checks that every image shape found in real sessions becomes a note, that the server strips uploads from older clients and cleans stored files, and that `client/media.py` and `server/media.py` are the same.
- `test_e2e.py` runs a real server process against a fake home folder (fake `~/.claude` and `~/.codex`). It checks: issue → install with `install.sh` → midnight split → resync → resend on request → auto-update (a release with a wrong hash is refused) → ending → zip → admin page → uninstall.

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.

---

<a id="한국어"></a>

# session-relay (한국어)

Claude Code와 Codex의 대화 기록을 하루 한 번 서버로 모으는 도구다. 사용자는 관리자에게 받은 **접속 코드**로 한 번 설치하고, 그 뒤로는 손댈 일이 없다.

## AI 에이전트용: 사용자 대신 설치하기

사용자가 Claude Code, Codex 같은 에이전트에게 이 저장소를 설치해 달라고 하면 다음 순서를 따른다.

1. 설치하면 무슨 일이 생기는지 사용자의 언어로 알리고, **접속 코드**를 묻는다. 접속 코드는 관리자가 주며 `SR-XXXX-XXXX-XXXX-XXXX` 모양이다. 알릴 내용은 다음과 같다.
   - 이 컴퓨터의 Claude Code·Codex 대화가 지금 한 번, 그 뒤로 하루 한 번 서버로 전송된다.
   - 대화 속 API 키·토큰·비밀번호 같은 비밀값과 이메일·전화번호 같은 개인정보는 이 컴퓨터에서 가린 뒤에 보낸다.
   - 종료일이 지나면 저절로 멈춘다.

   사용자가 코드가 든 안내문을 이미 붙여넣었다면 그 코드를 쓰고 다시 묻지 않는다.
2. 아래 명령을 실행한다. 저장소를 받을 필요가 없고, 코드를 주면 입력을 기다리지 않는다.
   ```bash
   curl -fsSL https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/main/install.sh | sh -s <CODE>
   ```
   저장소를 받았다면 `sh install.sh --code <CODE>`로도 된다.
3. 결과를 사용자에게 전한다.
   - **성공:** 누구로 설정됐는지, 종료일, 찾은 세션 파일 수, 첫 업로드가 백그라운드에서 진행 중이라는 것.
   - **"맞지 않습니다":** 코드를 확인해 달라고 한다. 코드를 추측하지 않는다.
   - **"이미 끝난":** 관리자에게 새 코드를 받아야 한다.
   - **python3 없음:** macOS에서는 `xcode-select --install` 뒤에 다시 실행한다.
4. 나중의 요청("상태", "지금 동기화", "멈춰", "새 코드")은 `~/.session-relay/relay status | sync | stop | init --code <CODE> | uninstall`로 처리한다. `~/.session-relay/README.md`에 정리되어 있다.

## 사용자 설치

관리자 웹에서 코드를 발행하면 아래 안내문이 만들어진다. 사용자는 둘 중 편한 방법 하나로 설치한다.

**1) Claude Code나 Codex에 맡기기**: 안내문을 붙여넣고 "설치해줘"라고 한다. 코드 없이 이 저장소 주소만 줘도 AI가 코드를 물어본다.

**2) 터미널 한 줄**
```bash
curl -fsSL https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/main/install.sh | sh -s SR-XXXX-XXXX-XXXX-XXXX
```
코드 없이 실행하면 터미널에서 코드를 물어본다.

설치하면 다음이 이 순서로 일어난다.
1. 서버에서 코드를 확인한다. 틀리거나 끝난 코드면 아무것도 설치하지 않는다.
2. `~/.session-relay/`에 프로그램을 복사한다.
3. 매일 동기화 작업을 등록한다. 맥의 launchd를 쓰고, 로그인할 때와 매시 깨어나되 서버에는 하루 한 번만 접속한다.
4. Claude Code·Codex용 스킬 `session-relay`를 설치한다. 대화창에서 "세션 릴레이 상태 알려줘"라고 물을 수 있게 하는 용도이고, `--no-skill`이면 빠진다.
5. 첫 업로드를 백그라운드에서 시작한다.

### 설치한 뒤

| 하려는 것 | 터미널 | Claude나 Codex에서 |
|---|---|---|
| 상태 보기 | `~/.session-relay/relay status` | "세션 릴레이 상태 알려줘" |
| 지금 보내기 | `~/.session-relay/relay sync` | "지금 동기화해줘" |
| 멈추기 | `~/.session-relay/relay stop` | "세션 전송 멈춰줘" |
| 코드 바꾸기 / 다시 시작 | `~/.session-relay/relay init --code SR-…` | "새 코드로 바꿔줘: SR-…" |
| 지우기 | `~/.session-relay/relay uninstall` | "세션 릴레이 지워줘" |
| 종료일이 지남 | 저절로 멈춤 | — |

메시지는 시스템 언어가 한국어면 한국어로, 아니면 영어로 나온다.

## 동작

- **하루 한 번, 이 순서로**: 작업은 로그인할 때와 매시 깨어난다.
  1. 그날 이미 보냈거나 종료일이 지났으면 서버를 부르지 않고 끝난다.
  2. 서버에 코드가 아직 유효한지 묻는다.
  3. 서버가 더 새 클라이언트를 알려 주면 먼저 업데이트한다([업데이트](#업데이트) 참고).
  4. 새로 생긴 것을 보낸다.
  5. 그날을 보냄으로 `~/.session-relay/state.json`에 기록하고 서버에 보고한다. 관리자 웹에는 마지막 동기화와 클라이언트 버전이 표시된다. 끝까지 성공해야 보냄으로 기록되므로, 실패하면 다음 정각에 다시 시도한다.

  컴퓨터가 꺼져 있던 날은 다음 로그인 때 보낸다.
- **날짜에 걸친 세션**: 각 줄을 그 줄의 시각(로컬 날짜)으로 나눈다. 17일 밤부터 18일 새벽까지 쓴 세션은 17일과 18일 폴더에 나뉘어 들어간다.
- **중복 방지**: (세션, 날짜) 조각마다 sha256을 `~/.session-relay/state.json`에 기록하고, 바뀐 조각만 다시 보낸다. 서버는 같은 조각을 덮어쓴다. 아침에 보낸 "오늘" 조각은 다음 날 완성본으로 바뀐다.
- **종료**: 저장된 종료 시점이 지나면 서버를 부르지 않고 멈춘다. 서버가 종료됐다거나 코드를 모른다고 답해도 멈춘다. 멈출 때 launchd 작업도 지운다.
- **비밀값과 개인정보는 가린 뒤 보낸다**: 아래 [민감 정보](#민감-정보)를 보라.
- **이미지는 글로 바꾼다**: 이미지와 그 밖의 base64 첨부(스크린샷, PDF)는 사용자 컴퓨터에서 `[image omitted: image/png, 245 KB]` 같은 표시로 바뀌어 아예 올라가지 않는다. 한 컴퓨터에서 재 보니 압축 후 업로드가 약 80% 줄었다. 옛 클라이언트가 보낸 업로드와 그 전에 저장된 파일은 서버가 같은 방식으로 바꾼다.
- **다시 보내기 요청**: 서버의 사본을 잃었을 때 관리자가 그 사용자의 세대 번호(epoch)를 올리면(`PATCH /admin/users/<id> {"resend": true}`), 그 컴퓨터는 다음 동기화 때 전부 다시 보낸다.
- **보내지 않는 것**: 서브에이전트 기록, `claude -p`와 `codex exec`로 실행된 세션, Codex가 Claude Code에서 가져온 복사본, 세션 안의 `api-request*` 줄과 `file-history-snapshot` 줄.
- **지원 환경**: 매일 작업은 macOS에서만 자동으로 등록된다. 클라이언트는 Python 표준 라이브러리만 쓰고, 맥 기본 python3(3.9)에서 돈다.

### 업데이트

설치된 컴퓨터는 스스로 업데이트한다. 다시 설치할 필요가 없다.

- 관리자가 `scripts/release.py`로 버전을 내보낸다([클라이언트 업데이트 내보내기](#클라이언트-업데이트-내보내기) 참고). 그 전에는 GitHub에 올려도 설치된 컴퓨터에는 아무 변화가 없다.
- 하루 한 번 확인할 때 서버의 응답에서 배포된 버전을 본다. 더 새 버전이면 그 커밋의 파일을 이 GitHub 저장소에서 받아, 서버가 준 sha256과 하나씩 대조한다. 그다음 새 코드를 한 번 시험 실행하고, 교체한 뒤(이전 버전은 `~/.session-relay/app.prev`에 남는다) 새 코드로 동기화한다.
- 파일은 이 저장소의 지정된 커밋에서 받아야 하고 서버의 해시와도 맞아야 한다. 그래서 GitHub나 서버 한쪽만으로는 사용자 컴퓨터에서 도는 코드를 바꿀 수 없다.
- 받기, 해시 대조, 시험 실행 중 하나라도 실패하면 지금 버전을 유지하고 이유를 로그에 남긴다. 동기화는 평소대로 하고, 업데이트는 다음 날 다시 시도한다.
- 0.6.0 이전에 설치한 컴퓨터에는 업데이트 기능이 없으므로 한 번은 직접 다시 설치해야 한다.

### 민감 정보

세션 기록에는 대화창에 입력한 내용만 있는 게 아니다. 에이전트가 실행한 명령의 출력과 읽은 파일 내용도 함께 남는다. 그래서 `.env` 파일, `cat ~/.aws/credentials` 출력, 붙여 넣은 키가 기록에 들어간다. **session-relay는 이런 값을 사용자 컴퓨터에서 가린 뒤에 보낸다.** 서버와 관리자는 원래 값을 받지 않는다. 가린 자리에는 `[redacted: github token]` 같은 짧은 표시가 남는다.

가리는 것은 다음과 같다.

- 형식이 알려진 API 키와 토큰: Anthropic·OpenAI(`sk-…`), GitHub, GitLab, AWS, Google, Slack, Stripe, Hugging Face, npm, SendGrid, JWT, session-relay 접속 코드
- 개인 키(`-----BEGIN … PRIVATE KEY-----` 블록)
- URL 안의 비밀번호(`postgres://user:비밀번호@host`)와 `Authorization: Bearer|Basic` 값
- 이름이 비밀값처럼 생긴 변수에 넣은 값. `.env`, 설정 파일, 코드, 명령어 속 `API_KEY=…`, `DB_PASSWORD: …`, `"client_secret": "…"`, `auth_token=…` 같은 것
- 이메일 주소: `@` 앞부분만 가리고 도메인은 남긴다(`[redacted: email]@gmail.com`). 어느 조직과 관련된 대화인지는 알 수 있게 하려는 것이다. `noreply`, `git@github.com`, `example.com` 주소는 그대로 둔다.
- 전화번호: 한국 번호(`010-1234-5678`, `01012345678`, `+82 10-…`, `02-123-4567`)와 `+`로 시작하는 해외 번호(`+1 415 555 1234`)
- 주민등록번호(`900101-1234567`처럼 하이픈이 있는 것)와 카드번호(16자리, Amex는 15자리이고 카드번호 검증식을 통과하는 것)

가리기는 패턴으로 찾는다(`client/redact.py`). 어느 패턴에도 맞지 않는 특이한 형식의 비밀값은 걸러지지 않을 수 있다. 이름, 주소, 회사·고객 이름은 정해진 형식이 없어 가리지 않는다. 에이전트가 읽은 고객의 소스 코드나 문서 내용도 가리지 않는다. 패턴이 바뀌면 각 컴퓨터는 다음 동기화 때 세션을 다시 읽어 달라진 조각을 보내고, 서버의 사본은 새로 가린 것으로 바뀐다.

## 관리자

| 폴더 | 무엇 | 어디서 |
|---|---|---|
| `client/`, `install.sh`, `skill/` | 사용자 컴퓨터에 설치되는 것 | 사용자 맥 |
| `server/` | 코드 발행·검증, 기록 저장, zip 다운로드 | Railway |
| `admin/` | 코드 발행·종료, 날짜별 다운로드 화면 | 관리자 맥 (127.0.0.1) |

### 서버 (Railway)

**현재 배포:** `https://session-relay-production.up.railway.app`
- 데이터는 볼륨 `/data`에 쌓인다.
- 서버 주소는 `client/defaults.json`에도 들어 있다.

코드를 고친 뒤 다시 배포할 때는 `cd server && railway up`을 실행한다. Railway에서 서버는 `/data`가 실제로 붙은 볼륨이 아니면 시작하지 않는다. 기록이 컨테이너의 임시 디스크에 쓰이는 일을 막기 위해서다. 첫 배포가 바로 그렇게 되어 다음 배포 때 기록을 모두 잃었다. 처음부터 새로 만들 때의 순서는 아래와 같다.

```bash
cd server
railway init --name session-relay
railway add --service session-relay --variables "ADMIN_KEY=$(openssl rand -hex 24)"
railway volume add --mount-path /data     # 볼륨이 붙을 때까지 기다린 뒤 railway up
railway up
railway domain
```

### 클라이언트 업데이트 내보내기

1. `client/relay.py`의 `VERSION`을 올리고, 테스트를 돌린 뒤, 커밋해서 `main`에 올린다.
2. 확인한 다음 내보낸다.
   ```bash
   python3 scripts/release.py --dry-run
   python3 scripts/release.py
   ```
   다음 경우에는 내보내지 않는다: `client/`나 `skill/`에 커밋하지 않은 변경이 있을 때, 그 커밋이 GitHub에 없을 때, GitHub이 다른 파일을 내줄 때, 버전이 지금 배포된 것보다 높지 않을 때.
3. 각 컴퓨터는 다음 하루 한 번 동기화 때 업데이트한다. 관리자 웹 상단에는 배포된 버전이, 사용자 화면에는 그 사용자의 클라이언트 버전이 나온다. 아직 업데이트하지 않은 사용자에게는 "대기" 표시가 붙는다.

### 관리자 웹

```bash
cp admin/config.example.json admin/config.json   # server_url, admin_key 채우기
python3 admin/admin.py                            # http://127.0.0.1:8787
```

- **새 코드 발행**: 전화번호, 메모, 종료일을 넣으면 코드와 사용자에게 보낼 안내문이 나온다. 안내문은 나중에 사용자 화면에서 다시 복사할 수 있다. 코드 원문은 `admin/data/codes.json`에만 남고, 서버에는 해시만 있다.
- **종료일 변경 / 지금 종료**: 사용자 컴퓨터는 다음 동기화 때 이를 알고 스스로 멈춘다.
- **클라이언트 버전**: 사용자 화면에 그 컴퓨터가 쓰는 클라이언트 버전이 나온다.
- **대화 기록**: 달력과 목록을 오갈 수 있다. 날짜를 누르면 그날의 세션 목록과 다운로드 버튼이 나오고, 기간을 정해 한꺼번에 받을 수도 있다. zip 안은 `<전화번호>/<날짜>/<도구>_<세션ID>.jsonl`과 날짜별 `_index.json`으로 되어 있다.

## 테스트

```bash
python3 tests/test_e2e.py
python3 tests/test_redact.py
python3 tests/test_media.py
```

- `test_redact.py`: 어떤 비밀값이 가려지는지, 평범한 코드와 문장은 그대로 남는지 확인한다.
- `test_media.py`: 실제 세션에서 찾은 이미지 모양이 모두 표시로 바뀌는지, 서버가 옛 클라이언트의 업로드와 이미 저장된 파일을 정리하는지, `client/media.py`와 `server/media.py`가 같은지 확인한다.
- `test_e2e.py`: 실제 서버 프로세스와 가짜 홈 폴더(가짜 `~/.claude`, `~/.codex`)로 다음 흐름을 확인한다. 발행 → `install.sh` 설치 → 자정 분할 → 재동기화 → 다시 보내기 요청 → 자동 업데이트(해시가 틀린 배포는 거부) → 종료 → zip → 관리자 웹 → 삭제.

## 라이선스

Apache License 2.0. `LICENSE`와 `NOTICE`를 보라.
