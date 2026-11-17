# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The operations team that runs session-relay, checking the admin page every day. Participants (hackathon or consulting-session members) never see the admin page; they only receive the install message and an access code.

## Product Purpose

session-relay collects participants' Claude Code and Codex conversation records once a day onto one server. The admin page is where the team issues and ends access codes, checks who is syncing, and pulls the records out. Success means the team can tell at a glance whose records are arriving and get any day's or range's conversations out without asking anyone.

## Positioning

Records leave the participant's computer already masked (secrets and personal information are replaced before upload), and nothing needs touching after a one-line install. The admin page shows what arrived, not a live feed of what people are typing.

## Operating Context

- Runs on the admin's own Mac at `http://127.0.0.1:8787` (`admin/admin.py`), proxying the Railway server with the admin key the browser never sees.
- Daily routine: open the page, scan participants for missing or stale syncs and outdated client versions, look into a person's days, download zips.
- Code issue flow: phone number + memo + end date, then copy the Korean install message and send it to the participant.
- Coming next (not built yet): analysing session conversations and producing reports from them. This is expected to become the most-used part of the admin page.

## Capabilities and Constraints

- One self-contained `admin/index.html`, plain HTML/CSS/JS, standard-library Python server, no build step. The page currently loads no external fonts, scripts or images.
- Korean UI. Participants are identified by phone number plus an optional memo.
- Data per participant: code (or its last digits), end date, first connection, last check, last sync, client version vs. released version, days, sessions, stored size; per day: sessions by tool (Claude / Codex), time span, project folder, lines, compressed size.
- Actions: issue code, copy code and install message, change end date, end now, download a day or a range as zip.
- The report/analysis feature's shape (what is measured, what a report contains) is undecided.

## Evidence on Hand

Real participant data lives on the server; the repository contains no screenshots, sample reports, or brand assets. No logo exists.

## Product Principles

1. The daily scan comes first: a stale sync or an outdated client must be visible without clicking.
2. The record is the product: dates, sessions and sizes are shown as precise numbers, never rounded into vague status words.
3. Nothing sensitive is shown that the server does not already hold; masking happens upstream and the page never implies otherwise.
4. Room for reading: reports will need long-form reading next to the operational lists, so the system must serve both.
