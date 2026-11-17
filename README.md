# session-relay

[English](#english) · [한국어](#한국어)

<a id="english"></a>

Collects Claude Code and Codex conversation records on a server, once a day. The user installs it once with an **access code** from the admin. After that there is nothing to do.

## For AI agents: installing this for the user

When a user asks you (Claude Code, Codex or another agent) to install this repository:

1. Tell the user, in their language, what installing does, then ask for their **access code** (it looks like `SR-XXXX-XXXX-XXXX-XXXX` and comes from the admin). Say this:
   - Every Claude Code and Codex conversation on this computer is sent to the session-relay server now, then once a day, until the code's end date.
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

- **Once a day**: if today was already sent, it ends without calling the server. Days when the computer was off are sent at the next login.
- **Sessions across midnight**: every line is filed under the local date of its own time. A session used from the night of the 17th into the early 18th lands in both the 17th and the 18th folders.
- **No duplicates**: the sha256 of every (session, date) slice is kept in `~/.session-relay/state.json`, and only changed slices are sent again. The server overwrites the same slice. "Today" sent in the morning is replaced the next day by the full day.
- **Ending**: once the stored end time has passed, it stops without calling the server. It also stops when the server says the code has ended or is unknown. Stopping removes the launchd job too.
- **Not sent**: subagent records, sessions run by `claude -p` and `codex exec`, copies Codex imported from Claude Code, and the `api-request*` and `file-history-snapshot` lines inside a session.
- **Platforms**: the daily job is registered automatically on macOS only. The client uses only the Python standard library and runs on the python3 that ships with macOS (3.9).

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

To redeploy after changing the code, run `cd server && railway up`. To set it up from scratch:

```bash
cd server
railway init --name session-relay
railway add --service session-relay --variables "ADMIN_KEY=$(openssl rand -hex 24)"
railway volume add --mount-path /data     # without it, records are lost on every deploy
railway up
railway domain
```

### Admin page

```bash
cp admin/config.example.json admin/config.json   # fill in server_url and admin_key
python3 admin/admin.py                            # http://127.0.0.1:8787
```

- **Issue a code**: enter a phone number, a memo and an end date to get the code and the message for the user. The message can be copied again later from the user's page. The code itself is kept only in `admin/data/codes.json`; the server keeps only its hash.
- **Change the end date / End now**: the user's computer learns it at its next sync and stops by itself.
- **Records**: switch between a calendar and a list. Click a date to see its sessions and a download button, or pick a range to download it all at once. The zip holds `<phone>/<date>/<tool>_<session id>.jsonl` and an `_index.json` per date.

## Tests

```bash
python3 tests/test_e2e.py
```

Runs a real server process against a fake home folder (fake `~/.claude` and `~/.codex`) and checks: issue → install with `install.sh` → midnight split → resync → ending → zip → admin page → uninstall.

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

- **하루 한 번**: 그날 이미 보냈으면 서버를 부르지 않고 끝난다. 컴퓨터가 꺼져 있던 날은 다음 로그인 때 보낸다.
- **날짜에 걸친 세션**: 각 줄을 그 줄의 시각(로컬 날짜)으로 나눈다. 17일 밤부터 18일 새벽까지 쓴 세션은 17일과 18일 폴더에 나뉘어 들어간다.
- **중복 방지**: (세션, 날짜) 조각마다 sha256을 `~/.session-relay/state.json`에 기록하고, 바뀐 조각만 다시 보낸다. 서버는 같은 조각을 덮어쓴다. 아침에 보낸 "오늘" 조각은 다음 날 완성본으로 바뀐다.
- **종료**: 저장된 종료 시점이 지나면 서버를 부르지 않고 멈춘다. 서버가 종료됐다거나 코드를 모른다고 답해도 멈춘다. 멈출 때 launchd 작업도 지운다.
- **보내지 않는 것**: 서브에이전트 기록, `claude -p`와 `codex exec`로 실행된 세션, Codex가 Claude Code에서 가져온 복사본, 세션 안의 `api-request*` 줄과 `file-history-snapshot` 줄.
- **지원 환경**: 매일 작업은 macOS에서만 자동으로 등록된다. 클라이언트는 Python 표준 라이브러리만 쓰고, 맥 기본 python3(3.9)에서 돈다.

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

코드를 고친 뒤 다시 배포할 때는 `cd server && railway up`을 실행한다. 처음부터 새로 만들 때의 순서는 아래와 같다.

```bash
cd server
railway init --name session-relay
railway add --service session-relay --variables "ADMIN_KEY=$(openssl rand -hex 24)"
railway volume add --mount-path /data     # 없으면 배포할 때마다 기록이 사라진다
railway up
railway domain
```

### 관리자 웹

```bash
cp admin/config.example.json admin/config.json   # server_url, admin_key 채우기
python3 admin/admin.py                            # http://127.0.0.1:8787
```

- **새 코드 발행**: 전화번호, 메모, 종료일을 넣으면 코드와 사용자에게 보낼 안내문이 나온다. 안내문은 나중에 사용자 화면에서 다시 복사할 수 있다. 코드 원문은 `admin/data/codes.json`에만 남고, 서버에는 해시만 있다.
- **종료일 변경 / 지금 종료**: 사용자 컴퓨터는 다음 동기화 때 이를 알고 스스로 멈춘다.
- **대화 기록**: 달력과 목록을 오갈 수 있다. 날짜를 누르면 그날의 세션 목록과 다운로드 버튼이 나오고, 기간을 정해 한꺼번에 받을 수도 있다. zip 안은 `<전화번호>/<날짜>/<도구>_<세션ID>.jsonl`과 날짜별 `_index.json`으로 되어 있다.

## 테스트

```bash
python3 tests/test_e2e.py
```

실제 서버 프로세스와 가짜 홈 폴더(가짜 `~/.claude`, `~/.codex`)로 다음 흐름을 확인한다: 발행 → `install.sh` 설치 → 자정 분할 → 재동기화 → 종료 → zip → 관리자 웹 → 삭제.

## 라이선스

Apache License 2.0. `LICENSE`와 `NOTICE`를 보라.
