---
name: Session Relay 관리
description: 참가자 한 명이 한 줄, 하루가 한 칸인 출석부 형식의 운영 화면
colors:
  ground: "#eef2ee"
  surface: "#ffffff"
  ink: "#1c2a3a"
  ink-2: "#4a5850"
  pencil: "#5d6a60"
  rule: "#c9d2ca"
  rule-soft: "#e1e7e2"
  weekend: "#f5f8f5"
  sel: "#e1eee6"
  sel-rule: "#93ad9c"
  red: "#c8322b"
  red-soft: "#fcefed"
  sat: "#3f6690"
  a1: "#cfe2d6"
  a2: "#8dbca1"
  a3: "#367a5b"
  a4: "#17483a"
  on-ink: "#ffffff"
  scrim: "rgba(28, 42, 58, .38)"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  figure:
    fontFamily: "-apple-system, BlinkMacSystemFont, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.2
    fontFeature: "tnum"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.45
  caption:
    fontFamily: "-apple-system, BlinkMacSystemFont, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.45
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.45
rounded:
  mark: "2px"
  control: "3px"
  dialog: "4px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "20px"
  section: "26px"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "32px"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "32px"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.red}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "32px"
  button-small:
    rounded: "{rounded.control}"
    padding: "0 9px"
    height: "26px"
    typography: "{typography.label}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "32px"
  tally-filter-on:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 9px"
    height: "30px"
  segmented-on:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    padding: "0 10px"
    height: "26px"
  tag:
    textColor: "{colors.ink-2}"
    rounded: "{rounded.mark}"
    padding: "0 5px"
    typography: "{typography.caption}"
  tag-warn:
    textColor: "{colors.red}"
    rounded: "{rounded.mark}"
    padding: "0 5px"
  day-mark-a1:
    backgroundColor: "{colors.a1}"
    rounded: "{rounded.mark}"
    size: "18px"
  day-mark-a2:
    backgroundColor: "{colors.a2}"
    rounded: "{rounded.mark}"
    size: "18px"
  day-mark-a3:
    backgroundColor: "{colors.a3}"
    rounded: "{rounded.mark}"
    size: "18px"
  day-mark-a4:
    backgroundColor: "{colors.a4}"
    rounded: "{rounded.mark}"
    size: "18px"
  day-mark-quiet:
    backgroundColor: "{colors.red-soft}"
    rounded: "{rounded.mark}"
    size: "18px"
  stamp-ended:
    textColor: "{colors.red}"
    rounded: "{rounded.mark}"
    padding: "0 2px"
    typography: "{typography.caption}"
  register-sheet:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  calendar-day:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.pencil}"
    rounded: "{rounded.mark}"
    padding: "4px 5px"
    height: "44px"
  dialog:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.dialog}"
    padding: "20px 22px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
---

# Design System: Session Relay 관리

## Overview

**Creative North Star: "출석부 (The Class Register)"**

관리 화면은 학급 출석부다. 참가자 한 명이 한 줄이고, 그 줄이 날짜 칸으로 이어진다. 빠진 날은 해석해야 하는 상태 단어가 아니라 곧은 줄 위의 빈 칸으로 보인다. 회녹색 바탕 위에 흰 장부가 놓이고, 청흑색 잉크로 쓰고, 가는 회녹색 괘선으로 나눈다. 연필 회색은 보조 기록, 4단계 초록은 하루 세션 수, 출석부의 붉은 펜은 결석과 종료에만 쓴다. "사이드바 목록 + 상세 카드"라는 흔한 관리자 배치를 따르지 않는다.

밀도는 높고 차분하다. 기본 글자 13px, 행 높이 44px, 숫자는 모두 고정폭 숫자(tabular-nums)로 정렬된다. 깊이는 그림자가 아니라 괘선의 굵기와 바탕의 단계로 만든다. 장식은 없고, 이 세계 고유의 장치는 날짜 칸, 기울어진 붉은 종료 도장, 일요일 빨강과 토요일 파랑의 요일 표기 셋뿐이다. 다크 모드는 같은 장부를 밤에 펼친 것으로, 같은 역할 토큰을 어두운 값으로 바꿀 뿐 구조는 그대로다.

다음 기능인 세션 대화 분석과 보고서는 이 페이지에서 가장 많이 쓰일 부분이 된다. 보고서는 새 세계를 만들지 않는다. 같은 장부 위에 읽기용 단을 하나 더 펼치는 것으로 확장한다(아래 Layout과 Components의 "보고서 읽기" 지침 참고, 아직 구현되지 않은 향후 지침).

**Key Characteristics:**
- 한 사람 한 줄, 하루 한 칸. 빈 칸 자체가 정보다.
- 흰 장부(surface)가 회녹색 바탕(ground) 위에 1px 괘선으로 놓인다. 그림자 없음.
- 붉은색은 결석·종료·경고에만. 단 일요일 빨강은 달력 관례로 예외.
- 고딕 한 벌과 모노 한 벌. 모노는 코드, 전화번호, 버전, 경로에만.
- 정확한 숫자를 그대로 보여준다. 반올림한 상태 단어로 바꾸지 않는다.

## Colors

차가운 회녹색 종이와 청흑색 잉크, 초록 농도 하나로 양을 말하고 붉은 펜 하나로 문제를 말하는 팔레트다. 모든 값은 `:root`의 CSS 사용자 속성이며 `prefers-color-scheme: dark`에서 같은 이름으로 바뀐다(다크 값은 `.impeccable/design.json`의 colorMeta에 기록).

### Primary
- **청흑 잉크 (Blue-Black Ink, `ink`)**: 본문 글자, 표 머리 아래 1px 굵은 괘선, 주 버튼과 선택된 분할 버튼의 바탕, 토스트 바탕, 포커스 링, 오늘 칸의 3px 밑줄. 이 화면의 "펜"이다.

### Secondary
- **출석부 빨강 (Register Red, `red`)**: 보고 없는 날(점선 칸), 종료된 코드와 종료 도장, "N일째 소식 없음" 경고, 위험 버튼(지금 종료), 오류 문구, 경고 태그. 일요일 열 머리와 달력 요일의 "일"도 이 색을 쓴다.
- **붉은 기 (Red Wash, `red-soft`)**: 보고 없는 날 칸의 옅은 바탕. 반드시 점선 빨강 테두리와 함께 쓴다.

### Tertiary
- **토요일 파랑 (Saturday Blue, `sat`)**: 토요일 열 머리와 달력 요일 "토", 그리고 Codex 도구 표시. 두 번째 범주색이 필요할 때 쓰는 유일한 비(非)초록 색이다.

### 세션 농도 (Session Scale)
- **새싹 (`a1`)** 1–2개, **잎 (`a2`)** 3–5개, **숲 (`a3`)** 6–9개, **깊은 숲 (`a4`)** 10개 이상. 출석부와 달력에서 같은 고정 구간을 쓴다. `a4`는 Claude 도구 표시색도 겸한다.

### Neutral
- **회녹 바탕 (Grey-Green Ground, `ground`)**: 페이지 바탕, 발급 코드와 안내문 미리보기 상자의 바탕.
- **장부 흰색 (Ledger White, `surface`)**: 출석부 시트, 상세 패널, 상단 바, 대화상자, 버튼과 입력칸.
- **보조 잉크 (`ink-2`)**: 태그 글자, 라벨, 경로, 탭되지 않은 집계 버튼 글자.
- **연필 (Pencil Grey, `pencil`)**: 날짜 아래 요일, 사실 목록의 항목명, 꼬리말, 종료된 행의 글자, 자리표시자.
- **괘선 (`rule`)**: 시트 테두리, 버튼·입력칸 테두리, 패널 경계.
- **옅은 괘선 (`rule-soft`)**: 행 구분선, 날짜 칸 사이 세로선, 빈 날짜 칸 테두리.
- **주말 음영 (`weekend`)**: 주말 열 바탕, 행 hover 바탕.
- **선택 (`sel`, `sel-rule`)**: 열린 행과 오늘 열의 바탕, 그 위 빈 칸의 강조 테두리.
- **잉크 위 글자 (`on-ink`)**, **막 (`scrim`)**: 잉크 바탕 위 글자, 대화상자 뒤 막.

### Named Rules
**The Red Pen Rule.** 빨강은 결석, 종료, 경고, 파괴적 동작에만 쓴다. 상태가 "괜찮음"인 것에는 절대 쓰지 않는다. 일요일 표기는 한국 달력의 관례이므로 이 규칙의 예외다.

**The One Scale Rule.** 양은 `a1`–`a4` 한 줄의 초록 농도로만 말한다. 구간(1–2 / 3–5 / 6–9 / 10+)은 화면마다 바꾸지 않는다.

## Typography

**Body Font:** 시스템 고딕 (-apple-system, Apple SD Gothic Neo, Malgun Gothic, Noto Sans KR)
**Label/Mono Font:** ui-monospace (SF Mono, Menlo, Consolas)

**Character:** 운영 장부의 글씨다. 고딕 한 벌로 제목부터 각주까지 쓰고, 기계가 만든 문자열(코드, 전화번호, 버전, 프로젝트 경로, 서버 주소)만 모노로 구분한다. 외부 글꼴을 불러오지 않는다. 지금 페이지는 바깥 글꼴·스크립트·이미지를 하나도 불러오지 않으며, 이 상태를 지키는 쪽을 택했다.

### Hierarchy
- **Headline** (700, 19px, 1.3): 상세 패널의 참가자 이름. 이름이 없으면 전화번호를 모노 17px로.
- **Title** (700, 16px, 1.3): 상단 바의 제품명, 대화상자 제목(아래 1px 잉크 괘선).
- **Figure** (700, 18px, 1.2, tnum): 집계 줄의 숫자. 화면에서 가장 큰 숫자는 개수다.
- **Body** (400, 13px, 1.45, tnum): 표 칸, 사실 목록, 세션 목록. 섹션 제목(h3)도 13px 굵게로, 크기가 아니라 굵기와 여백(26px 위)으로 구분한다.
- **Label** (600, 12px): 표 머리, 작은 버튼, 분할 버튼. 사실 목록 항목명은 같은 12px에 연필색 400.
- **Caption** (400, 11px): 요일, 범례, 태그, 도구 표시, 달력 날짜 숫자.
- **Mono** (400, 12px): 코드, 전화번호, 버전, 경로. 이름 자리에 올 때만 13px.

### Named Rules
**The Machine Text Rule.** 사람이 쓴 말은 고딕, 기계가 만든 문자열은 모노. 섞지 않는다.

**The Tabular Rule.** 모든 숫자는 `font-variant-numeric: tabular-nums`로 자릿수가 세로로 맞는다. 수치 열은 오른쪽 정렬.

## Layout

화면은 세 층이다. 높이 56px의 흰 상단 바(고정), 그 아래 전폭 출석부, 행을 누르면 오른쪽에 열리는 상세 패널. 패널 폭은 400px이고 1100px 이하에서 360px, 760px 이하에서는 출석부 아래로 내려간다. (방향 계약은 380px을 적었지만 구현은 400px이며, 구현을 기준으로 기록한다.)

출석부는 컨테이너 쿼리로 좁아진다. 940px 아래에서 종료일 열, 820px 아래에서 버전 열, 700px 아래에서 앞쪽 7일, 520px 아래에서 마지막 동기화와 합계 열을 숨기고 동기화 시각을 이름 아래로 옮긴다. 숨기는 순서는 "상세 패널이 다시 보여주는 것부터"다.

간격 리듬은 4 / 8 / 14 / 20 / 26px. 칸 사이 4–8px, 블록 안쪽 14px, 화면 가장자리 20px, 패널 안 섹션 사이 26px. 표 행 44px, 머리 46px.

### 보고서 읽기 (향후 표면 지침, 미구현)
보고서는 아직 없다. 아래는 같은 세계를 긴 글, 숫자, 차트로 넓히는 방법에 대한 지침이며 출시된 구성요소가 아니다.
- 보고서는 400px 상세 패널에 넣지 않는다. 긴 글을 읽기엔 좁다. 출석부 자리(전폭 영역)를 쓰거나 그 영역 안에 흰 시트를 하나 더 펼친다.
- 본문 단은 한글 기준 한 줄 약 40자 안팎(약 38–42em)으로 제한하고, 읽기용 본문은 기본 13px보다 키운 14–15px, 줄간격 1.7 정도로 시작한다. 확정되면 토큰으로 올린다.
- 숫자 표와 지표는 출석부와 같은 규칙: 머리 아래 1px 잉크 괘선, 행 사이 옅은 괘선, 수치 오른쪽 정렬, tabular-nums.
- 섹션은 13px 굵은 제목과 26px 위 여백으로 나눈다. 새 제목 크기를 만들지 않고 Headline(19px)과 Title(16px) 안에서 해결한다.

## Elevation & Depth

평평한 시스템이다. 콘텐츠에 떨어지는 그림자는 없다. 층은 바탕 단계(ground → surface)와 괘선 굵기(rule-soft 1px → rule 1px → ink 1px → ink 3px)로 만든다. `box-shadow`는 오직 안쪽 괘선을 긋는 도구로만 쓴다: 오늘 열과 오늘 달력 칸의 3px 잉크 밑줄, 열린 행의 1px 잉크 윗줄, 포커스된 세션 항목의 바탕을 좌우로 8px 늘이는 채움. 대화상자도 그림자 없이 테두리와 뒤의 막(scrim)만으로 떠 있다.

### Named Rules
**The Ruled Paper Rule.** 깊이는 선으로 긋는다. 흐린 그림자, 띄운 카드, 유리 효과를 쓰지 않는다. `box-shadow`가 필요하면 inset 선이거나 바탕 확장이어야 한다.

## Shapes

모서리는 거의 직각이다. 표식과 칸(날짜 칸, 태그, 도장, 달력 칸)은 2px, 조작부(버튼, 입력칸, 분할 버튼, 집계 버튼, 토스트)는 3px, 대화상자만 4px. 출석부 시트 자체는 0. 둥근 알약 모양과 원은 없다. 상태 점(`.ok`)도 7px 정사각형에 1px 모서리다.

유일하게 기울어진 형태는 종료 도장이다. 1.5px 빨강 테두리 안의 "종료" 두 글자를 -8도 돌려 찍는다.

## Components

### Buttons
장부 옆에 놓인 도장과 펜처럼 단단하고 조용하다.
- **Shape:** 거의 직각 (3px), 높이 32px, 글자 500.
- **기본:** 흰 바탕, 괘선 테두리. hover 시 테두리만 보조 잉크로 진해진다.
- **Primary:** 잉크 바탕에 흰 글자. 화면당 하나(상단 바의 "새 코드 발행", 대화상자의 확정 버튼). hover 시 불투명도 .88.
- **Danger:** 흰 바탕에 빨강 글자와 빨강 테두리. "지금 종료"처럼 되돌릴 수 없는 동작에만.
- **Small:** 26px, 12px 글자. 패널 안의 보조 동작.
- **Focus:** 전역 2px 잉크 윤곽선, 2px 띄움.

### 집계 필터 (Tally)
숫자가 곧 필터 버튼이다. 18px 굵은 개수 + 보조 잉크 라벨. 쉬는 상태는 테두리 없음, hover 시 괘선, 눌림(aria-pressed) 시 흰 바탕과 잉크 테두리. 경고 항목(소식 없음)은 개수가 있을 때만 숫자와 라벨이 빨강.

### Chips / Tags
- **Tag:** 1px 괘선 테두리, 2px 모서리, 11px 보조 잉크 글자, 줄높이 17px. 설치 전, 사용 중, 최신 대기 같은 짧은 상태.
- **Tag warn:** 테두리와 글자가 빨강.
- **Tool:** 같은 모양에 테두리가 글자색(currentColor). Claude는 `a4`, Codex는 `sat`.

### 분할 버튼 (Segmented)
1px 괘선 테두리 안에 26px 버튼이 붙어 있고 사이는 1px 괘선. 선택된 쪽은 잉크 바탕에 흰 글자. 달력/목록 전환에 쓴다.

### Inputs / Fields
- **Style:** 32px, 1px 괘선 테두리, 3px 모서리, 흰 바탕, 연필색 자리표시자. 라벨은 입력칸 위 12px 보조 잉크, 5px 간격.
- **Focus:** 전역 2px 잉크 윤곽선.
- **Error:** 폼 아래 빨강 문구.

### 출석부 (Register) — 대표 구성요소
흰 시트, 1px 괘선 테두리, 모서리 없음. 머리 46px에 아래 1px 잉크 괘선. 행 44px, 행 사이 옅은 괘선. 날짜 열은 옅은 세로 괘선으로 나뉘고, 주말 열은 주말 음영, 오늘 열은 선택 바탕과 머리의 3px 잉크 밑줄. 열린 행은 선택 바탕에 위아래 잉크 선. 종료된 행은 글자를 연필색으로 낮춘다. 참가자 칸은 이름(600) 위, 전화번호(모노 11px 연필색) 아래.

### 날짜 칸 (Day Mark)
18px 정사각형, 2px 모서리. 빈 날은 옅은 괘선 테두리만, 세션이 있으면 `a1`–`a4`로 채운다. 마지막 보고 이후의 날은 빨강 점선 테두리 + 붉은 기 바탕. 코드 발급 전의 날은 테두리 없음, 미래·불러오는 중은 옅은 괘선 바탕에 불투명도 .6. 선택 행이나 오늘 열 위의 빈 칸은 `sel-rule` 테두리로 진하게 해 줄이 끊기지 않게 한다.

### 종료 도장 (Ended Stamp)
1.5px 빨강 테두리, 2px 모서리, 빨강 11px 굵은 "종료", -8도 회전. 종료일 칸과 상세 패널 머리에만 찍는다. 종료가 아닌 어떤 상태에도 이 모양을 빌려 쓰지 않는다.

### 사실 목록 (Facts)
92px 항목명 열 + 값 열의 격자. 위 1px 괘선, 항목마다 아래 옅은 괘선, 9px 위아래 여백. 항목명은 연필색 12px. 값 아래에 small 버튼 묶음이 붙을 수 있다.

### 월 달력 (Calendar)
7열 격자, 3px 간격. 칸은 44px 높이, 옅은 괘선 테두리, 2px 모서리, 왼쪽 위 날짜(11px), 오른쪽 아래 세션 수(13px 600). 세션 농도는 출석부와 같은 `a1`–`a4`. 보고 없는 날은 빨강 점선, 오늘은 3px 잉크 밑줄, 선택된 날은 2px 잉크 윤곽선. 다가올 날은 테두리와 바탕이 없다.

### 세션 목록
위 1px 잉크 괘선, 항목 사이 옅은 괘선. 첫 줄은 도구 표시 + 시각 범위, 둘째 줄은 모노 12px 경로. 포커스된 항목은 선택 바탕을 좌우로 8px 넓힌다.

### Dialogs / Toast
- **Dialog:** 최대 520px, 1px 괘선, 4px 모서리, 20px 22px 안쪽 여백, 제목 아래 1px 잉크 괘선, 뒤에 잉크빛 막. 확정 버튼은 오른쪽 끝.
- **발급 코드 / 안내문 상자:** 회녹 바탕에 괘선 테두리. 코드는 모노 20px 600.
- **Toast:** 화면 아래 가운데, 잉크 바탕 흰 글자, 3px 모서리, 0.2초 불투명도 전환.

### 보고서 구성 (향후 표면 지침, 미구현)
- **긴 글:** 흰 시트 위에, 위 Layout의 읽기 단 규칙으로. 대화 원문 인용은 이미 있는 안내문 상자 형식(회녹 바탕, 옅은 괘선, pre-wrap)을 빌려 쓴다. 기계가 만든 문자열(경로, 명령, 코드)은 모노.
- **지표:** 큰 숫자는 Figure(18px 700)까지만. 숫자 옆에 단위와 기간을 붙여 정확하게 적는다.
- **차트:** 새 색을 만들지 않는다. 양은 `a1`–`a4` 순차 농도, 두 범주 비교는 Claude `a4` 대 Codex `sat`, 결측과 경고는 빨강 점선. 축과 격자선은 `rule-soft` 1px, 기준선은 `ink` 1px. 날짜×참가자 같은 격자 차트는 날짜 칸 표식을 그대로 키워 쓴다. 그라디언트, 그림자, 둥근 막대 끝을 쓰지 않는다.

## Do's and Don'ts

### Do:
- **Do** 하루를 한 칸으로 보여주고, 빠진 날을 빈 칸이나 빨강 점선 칸으로 남긴다.
- **Do** 양은 `a1`–`a4` 한 단계 척도(1–2 / 3–5 / 6–9 / 10+)로만 표시한다.
- **Do** 깊이를 괘선 굵기와 바탕 단계로 만든다: 행 사이 `rule-soft`, 표 머리 아래 `ink` 1px, 오늘 표시 `ink` 3px inset.
- **Do** 코드, 전화번호, 버전, 경로는 모노, 그 밖의 모든 글은 고딕으로 쓴다.
- **Do** 숫자를 정확히 쓰고 tabular-nums로 정렬하며, 수치 열은 오른쪽 정렬한다.
- **Do** 일요일은 빨강, 토요일은 `sat` 파랑으로 표기하고 주말 열에 `weekend` 음영을 깐다.
- **Do** 새 색을 쓰기 전에 다크 모드 값까지 같은 이름의 토큰으로 정의한다.

### Don't:
- **Don't** 빨강을 결석, 종료, 경고, 파괴적 동작, 일요일 표기 밖에서 쓰지 않는다.
- **Don't** 콘텐츠에 흐린 그림자나 띄운 카드를 쓰지 않는다. `box-shadow`는 inset 선과 바탕 확장에만.
- **Don't** 4px보다 둥근 모서리, 알약 모양, 원형 배지를 쓰지 않는다.
- **Don't** 종료 도장의 기울어진 모양을 종료 외의 상태에 빌려 쓰지 않는다.
- **Don't** 빠진 날을 "비활성", "주의" 같은 상태 단어로 바꿔 숨기지 않는다.
- **Don't** 사이드바 목록 + 상세 카드 배치로 되돌아가지 않는다. 목록은 출석부다.
- **Don't** 런타임에 외부 글꼴이나 아이콘 자산을 불러오지 않는다. 아이콘은 인라인 SVG.
