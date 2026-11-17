# session-relay

사용자 컴퓨터의 Claude Code·Codex 대화 기록을 하루 한 번 서버로 모으는 도구.

| 폴더 | 무엇 | 어디서 |
|---|---|---|
| `skills/session-relay`, `skills/session-relay-init` | 사용자 컴퓨터에 까는 스킬 (Claude Code + Codex) | 사용자 맥 |
| `server/` | 코드 발행·검증, 기록 저장, zip 다운로드 | Railway |
| `admin/` | 코드 발행·종료, 날짜별 다운로드 화면 | 관리자 맥 (127.0.0.1) |

모두 Python 표준 라이브러리만 쓴다. 스킬은 맥 기본 python3(3.9)에서 돈다.

## 1. 서버 배포 (Railway)

**현재 배포:** `https://session-relay-production.up.railway.app`
- Railway 프로젝트는 `session-relay`, 서비스도 `session-relay`다.
- 볼륨 `session-relay-volume`이 `/data`에 붙어 있다.
- `ADMIN_KEY`는 Railway 변수와 `admin/config.json`에 있다.

코드를 고친 뒤 다시 배포할 때는 `cd server && railway up`을 실행한다. 처음부터 새로 만들 때의 순서는 아래와 같다.

```bash
cd server
railway init                       # 새 프로젝트
railway up                         # Dockerfile로 빌드
railway volume add --mount-path /data
railway variables --set ADMIN_KEY=$(openssl rand -hex 24)
railway domain                     # 공개 주소 발급
```

볼륨이 없으면 배포할 때마다 기록이 사라진다. 서버는 `RAILWAY_VOLUME_MOUNT_PATH`를 데이터 폴더로 쓴다.

## 2. 관리자 웹

```bash
cp admin/config.example.json admin/config.json   # server_url, admin_key 채우기
python3 admin/admin.py                            # http://127.0.0.1:8787
```

- **새 코드 발행**: 전화번호, 메모, 종료일을 넣으면 코드와 사용자에게 보낼 안내문이 나온다. 코드 원문은 `admin/data/codes.json`에만 남는다(서버에는 해시만 있다).
- **종료일 변경 / 지금 종료**: 사용자 컴퓨터는 다음 동기화 때 이를 알고 스스로 멈춘다.
- **대화 기록**: 달력과 목록을 오갈 수 있다. 날짜를 누르면 그날의 세션 목록과 다운로드 버튼이 나오고, 기간을 정해 한꺼번에 받을 수도 있다. zip 안은 `<전화번호>/<날짜>/<도구>_<세션ID>.jsonl`과 날짜별 `_index.json`으로 되어 있다.

## 3. 사용자에게 배포

```bash
sh install.sh
```

서버 주소는 `skills/session-relay/scripts/defaults.json`에 들어 있다. 주소가 바뀌면 `sh install.sh --server <새 주소>`로 실행한다.

`~/.claude/skills`와 `~/.agents/skills`(Codex)에 두 스킬을 설치한다. 그다음 Claude Code나 Codex에서 `session-relay-init`을 실행하고 코드를 넣으면 된다.

## 동작

- **하루 한 번**: launchd 작업이 로그인할 때와 매시 정각마다 깨어나지만, 그날 이미 보냈으면 서버를 부르지 않고 끝난다.
- **날짜에 걸친 세션**: 각 줄을 그 줄의 시각(로컬 날짜)으로 나눈다. 17일 밤부터 18일 새벽까지 쓴 세션은 17일과 18일 폴더에 나뉘어 들어간다.
- **중복 방지**: (세션, 날짜) 조각마다 sha256을 `~/.session-relay/state.json`에 기록하고, 바뀐 조각만 다시 보낸다. 서버는 같은 조각을 덮어쓴다. 아침에 보낸 "오늘" 조각은 다음 날 완성본으로 바뀐다.
- **종료**: 저장된 종료 시점이 지나면 서버를 부르지 않고 멈춘다. 서버가 종료됐다거나 코드를 모른다고 답해도 멈춘다. 멈출 때 launchd 작업도 지운다.
- **보내지 않는 것**: 서브에이전트 기록, `claude -p`와 `codex exec`로 실행된 세션, Codex가 Claude Code에서 가져온 복사본, 세션 안의 `api-request*` 줄과 `file-history-snapshot` 줄.

## 테스트

```bash
python3 tests/test_e2e.py
```

실제 서버 프로세스와 가짜 `~/.claude`·`~/.codex`로 발행부터 init, 자정 분할, 재동기화, 종료, zip, 관리자 웹까지 확인한다.
