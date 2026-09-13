# Icons everywhere + live broadcast delivery

Two changes. Both frontend and backend only — **no APK rebuild needed.**

---

## 1. Icons on every page

Every page header now shows the same icon the sidebar uses for that route,
beside the title.

**Files**
- `frontend/src/nav/navConfig.js` — new `iconForPath()`
- `frontend/src/components/domain/index.jsx` — `PageHeader` resolves it

**Why it was done this way.** The obvious approach is an `icon` prop on each
page. That is 70 edits now and 70 chances to pass the wrong one later, and the
first time somebody changes a sidebar icon the page header disagrees with the
menu item the user just clicked.

Instead the icon is looked up from the nav config, which already maps every
route to an icon. One source of truth, and a new module gets its page icon the
moment it gets its sidebar entry — no second list to remember.

Verified against all 64 routes:

```
/app/rooms      -> DoorOpen        /app/invoices   -> ReceiptIndianRupee
/app/beds       -> BedDouble       /me/rent        -> ReceiptIndianRupee
/app/property   -> Layers3         /master/settings-> Settings
/app/residents  -> Users
```

Longest match wins, so `/app/residents/<id>` gets the residents icon rather
than whichever shorter route was declared first. Pages not in the nav at all
(detail screens, wizards) can pass `icon={SomeIcon}`, or `icon={false}` to
turn it off.

---

## 2. Live broadcast delivery

**Before:** "Queued for 61 people." Then nothing. No way to tell a working
system from a broken one.

**Now:** after sending, the counts poll every 3 seconds and climb.

| Number | Means |
|---|---|
| **In the app** | Rows written — everyone who will see it in their bell |
| **On phones** | Firebase accepted it |
| **Read** | They opened it |
| **Queued** | Still waiting for the sweep |
| **No phone** | No app installed, or notifications turned off |

Polling stops when the queue is empty, not on a timer — a slow batch is never
reported as finished while rows are still going out.

**Before sending**, three honest numbers replace the one misleading one:

- **Total users** — everyone who gets it in the app
- **Notifications on** — how many have not switched it off
- **Will buzz** — how many have a phone actually registered

"61 people" when one phone was registered was the thing that sent us chasing a
non-existent bug. Now the gap is visible before you press send.

"Will buzz" counts **people**, not devices. Two phones on one account is one
person who gets alerted, not two.

**Files**
- `backend/app/api/v1/endpoints/master.py` — broadcast id, `/broadcast/{id}/stats`, `/broadcasts`, richer `/broadcast/reach`
- `frontend/src/pages/master/BroadcastCard.jsx`
- `frontend/src/services/api/platformSettingsApi.js`

**How the stats work.** Each broadcast now generates a UUID that every one of
its notification rows carries in `entity_id`. The counts are `GROUP BY` over
those rows.

There is deliberately no `broadcasts` table. A broadcast is not something
anybody edits or deletes — it is something that happened — and a second table
would only be a copy of these rows that can drift out of step with them.

---

## Deploy

```powershell
cd C:\Users\DELL\Downloads\pgdesk-release-final\pgdesk
git add -A
git commit -m "Icons on every page header, live broadcast delivery counts"
git push origin main
```

**No migration.** No new columns — the stats are computed from rows that
already exist.

**No APK rebuild.** Both changes are backend and web, so the installed app
picks them up on next open.

After Render goes green: hard refresh with **Ctrl+Shift+R**, or you will see
cached JavaScript and think nothing deployed.

---

## Test

| # | Test | Expected |
|---|---|---|
| 1 | Open Rooms, Beds, Buildings, Residents | Icon beside each title, matching the sidebar |
| 2 | Open a resident's detail page | Residents icon, not a wrong one |
| 3 | Master → Settings → Broadcast | Three counts before sending: total / notifications on / will buzz |
| 4 | Send a broadcast, watch the card | Counts appear and climb, "Sending…" then "Finished" |
| 5 | Open it on the phone | "Read" count goes up within a few seconds |
| 6 | Turn your own notifications off, broadcast again | You land in "No phone", bell still shows it |

Test 5 is the one that proves the whole loop — sent, delivered, opened, counted.
