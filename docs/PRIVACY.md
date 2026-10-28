# Privacy design

Public-facing text: `frontend/app/about/page.tsx` (data collection policy) and `frontend/app/privacy/page.tsx`.
This document records the design decisions behind them.

## Principles

1. **Collect only what the game shows.** The addon uses Blizzard's addon API only: no memory reading, no code
   injection, no network access, no automation.
2. **Minimise contributor data.** A contributor is an HMAC (keyed with `CONTRIBUTOR_ID_SALT`) of the addon's random
   installation ID. There are no accounts, e-mail addresses or IP addresses.
3. **Never claim identity or skill we cannot prove.** Profiles say "observed history", carry "not claimed / does not
   identify the account owner" notices, and label every number with its provenance.
4. **Easy correction and opt-out.** A public report form needs no contact details; suppression hides a profile from
   search and from other players' run lists.

## What is stored

| Data | Purpose | Retention |
|---|---|---|
| Character names, surnames, GUIDs, class, race, level, role | Character histories | While the character is public; suppressed profiles stay hidden |
| Dungeon runs, encounters, deaths, meter totals, equipment | Histories and statistics | Indefinitely, for recalculation |
| Raw observations (validated payloads) | Audit and reprocessing | Indefinitely; invalidated rows are kept for audit, not shown |
| Contributor HMAC and counters | Deduplication and abuse control | Indefinitely |
| Upload batch metadata (digests, counts, errors) | Idempotency and support | Recommended: purge records older than 180 days except digests (not automated yet; see READINESS) |
| Data reports (free text) | Moderation | Until resolved, plus 1 year |
| IP addresses | Rate limiting only | **Never stored**: hashed with an in-memory salt that changes on restart; removed from proxy logs by the Caddy log filter; uvicorn access logs disabled |

## Suppression process

1. Someone submits a `suppression_request` (report form, or the link on the profile).
2. A moderator reviews it in `GET /api/v1/admin/reports`. Because the request is low-risk and protects privacy, the
   default is to grant it unless it looks like harassment of another player (e.g. mass requests).
3. `POST /api/v1/admin/characters/{id}/visibility {"visibility": "suppressed"}`. The profile returns HTTP 410, search
   excludes it, and run pages show "Hidden character" with no metrics.
4. Resolve the report (`POST /api/v1/admin/reports/{id}/resolve`).

Future uploads still record the character, which keeps runs consistent for everyone else, but the character remains
hidden.

## Profile claims

`claim_status` exists (`unclaimed` / `pending` / `verified`) but no claim flow is implemented. Any self-reported proof
(an addon record, a code typed in game) can be forged by editing SavedVariables. A claim feature should wait for a
verifiable mechanism, for example Blizzard's OAuth character API if it covers Forever characters, and must not show
a "verified owner" badge before then.

## Before public distribution: terms review (open action item)

Not yet done. Before releasing the addon and opening the site, review the current versions of:

* Blizzard's UI Add-On Development Policy (historically: add-ons must be free, unobfuscated, free of in-game
  advertising and requests for donations in the UI, and must not harm realm performance);
* the World of Warcraft Terms of Use / EULA, and any rules specific to World of Warcraft: Forever;
* trademark guidelines for using "World of Warcraft" in the site's name and text (the site already states it is not
  affiliated with Blizzard);
* data-protection obligations for the hosting region (e.g. GDPR if serving EU players: lawful basis for publishing
  gameplay observations about other players, the right to object, which suppression serves, and a contact for
  requests).
