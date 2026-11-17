---
version: 1
slug: "admin-index-html"
primary_target: "admin/index.html"
related_targets: []
---

# Admin page (admin/index.html)

Mode: Operate. The operations team opens it every morning to see who is syncing, who has gone quiet and who runs an old client, then drills into one participant's days and downloads zips. Session analysis and reports come next and will live on this same page; they are not built yet.

## Direction contract

THESIS: The admin page is a class register. Every participant is one row that runs into day cells, so a missed day shows as an empty cell in a straight line, not a status word to decode. It refuses the stock "sidebar list + detail card" admin layout.

OWN-WORLD: Cool grey-green ground (#eef2ee), white table surface, blue-black ink (#1c2a3a), thin grey-green rules, a pencil grey for secondary text, and a 4-step green scale for sessions per day. Register red (#c8322b) is only for missed days, ended codes and the quiet-for-days alert. Ended codes carry a tilted red 종료 stamp. Weekend columns: 일 in red, 토 in blue, both shaded faintly. Radius 2–4px, no shadows on content, one gothic family plus mono for codes, phone numbers and versions.

STORY: The team sees at once who synced today and who has gone quiet (red dashed cells). They click a row, check the facts on the right, download a range, copy the install message or change the end date.

FIRST VIEWPORT: White top bar with the product name, server and released version, search, 새로고침 and a dark 새 코드 발행 button. A tally line underneath (오늘 동기화 · N일째 조용함 · 구버전 · 종료) with the colour legend. Then a full-width register: 전화번호 / 메모 / 종료일 / 마지막 동기화 / 버전 / the last 14 day cells / 14일 세션. Clicking a row opens a 380px detail panel on the right with facts, actions, a month calendar or list, and that day's sessions.

FORM: attendance register (출석부), candidate 1 on the ordered list (picked over the rolled direction, 개표 방송). seed:3ceeb147142a9b8d

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
