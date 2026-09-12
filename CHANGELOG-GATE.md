# Gate scanning and resident self check-in

Everything in this release concerns one screen and one question: how a movement
at the gate gets recorded.

---

## Read this first: the APK in `landing/` is stale

`landing/pgguru.apk` is the **previous** build. It predates everything below, so
it has no camera scanning and no self check-in — installing it and finding no
camera would look like this work failed.

Rebuild it before testing on a phone:

```bash
cd frontend
npm install          # four new packages, listed below
npm run build:android
```

`build:android` runs `cap sync android`, which registers the new native plugins.
Skipping it produces an APK where the scanner silently does nothing.

---

## What was actually broken

Three separate things, all of which had to be fixed for any of it to work. Only
the first was obvious.

**1. The camera was never built.** Not broken — absent. `AndroidManifest.xml`
declared exactly one permission (`INTERNET`); no camera or barcode plugin was
installed; and the staff `Scan.jsx` screen was a bare text box whose hint told
guards to let a hardware scanner type into it.

**2. The resident's QR was not a QR.** `MyScan.jsx` contained a `QrCanvas`
function that hashed the token and drew a 21×21 grid of squares from it. It
looked convincing to a person and could not be decoded by any scanner in
existence. The comment in the code admitted as much. This was the real blocker:
adding a camera without fixing this would have produced a scanner pointed at
something permanently unreadable.

**3. Nothing scanned the gate.** There was no gate identity at all — no token,
no coordinates, no way for a resident to record their own movement.

---

## The two directions

Both are live. Both write to `gate_logs`, told apart by `source`. Neither
replaces the other.

| Flow | Endpoint | `source` | Needs |
|---|---|---|---|
| Guard scans resident | `POST /scan` (staff) | `qr` | the resident's card or phone screen |
| Resident scans gate | `POST /me/scan` (resident) | `self` | a smartphone, GPS, and the gate poster |

The guard flow stays because a resident without a smartphone, or with a flat
battery, is not a reason to have no attendance record.

### Why self check-in needs two checks, not one

It inverts who writes the record. With a guard scanning, the writer is a trusted
employee. With self check-in, the writer is the person who benefits from the
record being wrong.

- **The gate QR alone proves nothing.** It is printed on a wall, so it leaks by
  design — one photograph forwarded on WhatsApp and a friend marks himself
  present from another city.
- **GPS alone proves nothing.** Mock-location apps are free and do not need
  root.

Together they are meaningfully harder: an absent resident needs a photograph of
a code they could only obtain by being there, *plus* a spoofing app, *plus* a
willingness to leave a false position in an append-only log staff can read.

That is a deterrent proportionate to a hostel attendance register. It is not
proof of presence, and the code says so — in the service docstring, the README
and the owner-facing setup screen — rather than implying otherwise. Every self
check-in stores `latitude`, `longitude`, `accuracy_m` and `distance_m`
**including refused attempts**, so a pattern of impossible positions is
reviewable after the fact.

---

## Three pre-existing bugs found while testing this

None of these were in the request. They surfaced from running the system rather
than trusting it, and two of them were in code that shipped.

**Negative-duration permanent lockout.** The duplicate-scan guard computed
`now - last_scan < window`. A gate log dated in the future makes that difference
negative, and negative is below any window — so it reads as "scanned a moment
ago" and keeps reading that way forever. The guard's screen was printing
`Already scanned -4867s ago`. A resident is locked out of the gate permanently
by a timestamp nobody can see. Present in the original staff scan; fixed in both
paths with an absolute gap.

**Future-dated rows poisoning "last movement".** The lookup ordered by
`occurred_at DESC`, so a future row sits permanently at the top and becomes the
last movement. Two things then break silently at once: direction inference
alternates from an event that has not happened, and the duplicate window
compares against the wrong row. Now excluded via `occurred_at <= now`. The
root cause was `seed_operations.py` writing today's 7pm return even when the
seed ran in the morning; that is fixed too.

**The Security role could not scan.** Its seed description reads *"Gate duty -
scanning, visitor entry and gate pass checks"* and its permission list contained
no `scan.*` entry at all. Every code returned 403. It stayed hidden because the
frontend hides the page without `scan.view`, so a missing permission looked
identical to a missing feature. Added `scan.view` and `scan.manage`.

---

## QR payload format

```
PGD1:R:<token>    a resident's card
PGD1:G:<token>    a gate's code
```

Defined in `backend/app/utils/qr_payload.py`, mirrored in `frontend/src/lib/qr.js`.
Change one, change the other in the same commit.

The prefix exists mainly for the client. A camera pointed at a gate decodes the
UPI sticker beside it, courier labels and posters; without a marker every one of
those becomes a request that returns "not recognised", indistinguishable from a
genuinely unknown resident, which teaches guards to ignore the message. Bare
tokens still parse, so cards printed before this format and hardware barcode
guns keep working unchanged.

---

## Setup, once per branch

`Branches → Gate` (needs `branches.edit`). Stand at the gate, tap **Use my
current location**, set a radius, switch self check-in on. A gate code is issued
on save and the same screen prints an A4 poster. **Reissue** invalidates every
printed copy immediately — the response to a code believed to be circulating.

**On the default 150 m radius.** Phone GPS beside a building in an Indian city is
routinely 20–50 m out. A fence that does not absorb that error refuses residents
who really are standing at the gate, and nobody traces those support calls back
to a number typed once during setup. Separately, a reading worse than 100 m
accuracy is refused outright rather than believed — accepting it would make any
radius decorative for anyone indoors.

---

## Scanning

Android uses Google's ML Kit via `@capacitor-mlkit/barcode-scanning`, which opens
its own native screen — it focuses and decodes far better than anything in a
WebView, which matters at a gate at 11pm. The browser falls back to
`getUserMedia` plus jsQR.

**A browser camera requires https.** Over plain `http://`, `getUserMedia` does
not exist. This is the most common cause of a scanner that appears broken, and
the error message says so explicitly.

---

## Changes

### New — backend

| File | Purpose |
|---|---|
| `app/utils/geo.py` | Haversine distance, coordinate validation |
| `app/utils/qr_payload.py` | The payload format, parsing and generation |
| `app/services/self_checkin_service.py` | The whole resident-scans-gate flow |
| `alembic/versions/0008_gate_geofence.py` | Schema |
| `tests/test_self_checkin.py` | 25 tests |

### New — frontend

| File | Purpose |
|---|---|
| `src/lib/qr.js` | Payload format, mirroring the backend |
| `src/lib/geo.js` | Geolocation with useful failure messages |
| `src/lib/scanner.js` | ML Kit and getUserMedia behind one call |
| `src/components/ui/QrCode.jsx` | A real, scannable QR |
| `src/components/ui/Scanner.jsx` | The camera UI |
| `src/pages/org/GateSetup.jsx` | Owner setup and printable poster |

### Schema

`branches` gains `gate_qr_token`, `latitude`, `longitude`, `geofence_radius_m`,
`self_checkin_enabled`. `gate_logs` gains `latitude`, `longitude`, `accuracy_m`,
`distance_m`.

Every column is nullable or carries a server default, so the migration is safe
to apply while the previous release is still serving. Existing branches simply
have self check-in off until an owner positions them.

### API

```
GET    /api/v1/me/gate                       am I close enough, and why not
POST   /api/v1/me/scan                       resident records their movement
PUT    /api/v1/branches/{id}/location        set the gate position and geofence
POST   /api/v1/branches/{id}/gate-token      issue a new gate QR
```

### Android

`CAMERA`, `ACCESS_FINE_LOCATION` and `ACCESS_COARSE_LOCATION` added. Camera and
GPS are declared `required="false"` — staff use this on desks and tablets that
may have neither, and a required feature would hide the app from those devices
in the Play Store entirely.

---

## Verification

- **301 backend tests pass**, up from 276.
- The migration drift test runs `alembic upgrade head` from an empty database
  and compares it column-by-column against the models. It passes, so the
  migration and the models agree.
- The QR output was decoded with an independent reader (OpenCV) to prove it is
  genuinely scannable rather than assumed to be.
- The full flow was exercised over real HTTP against live Postgres: refused from
  3.3 km away, refused on a 400 m accuracy reading, accepted at the gate with
  attendance written as `source='self'`, double-tap suppressed, a resident card
  scanned into the gate endpoint correctly named as the wrong code type.

```bash
cd backend
python -m pytest
python -m alembic upgrade head
python seed.py
```

---

## Not done

- **No frontend tests.** Unchanged from before; the suite is backend-only.
- **One gate per branch.** A branch with two entrances needs a `gates` table.
  Deliberately deferred — it is a schema change, not a patch.
- **Biometric.** Deferred by agreement. `GateLog.source` and
  `Attendance.source` are free strings already carrying `qr` and `self`, so
  adding `biometric` needs no schema change to those two columns — a devices
  table, an enrollment mapping and a device-key-authenticated endpoint are the
  work.
- **The geofence trusts the phone.** No mock-location detection. Android exposes
  `isFromMockProvider()` but the Capacitor Geolocation plugin does not surface
  it. Storing every position was the deliberate alternative: detection after the
  fact rather than prevention.
