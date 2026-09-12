# Play Store submission pack — PGuru

Everything to paste into Play Console. Written against what the app actually
does, not from a template.

Developer account: **Dygine Software Solutions** (personal account, ID
4795439278644059126). Signed AAB at
`frontend/android/app/build/outputs/bundle/release/app-release.aab`.

---

## 1. Store listing

### App name (30 characters max)
```
PGuru — PG & Hostel Manager
```

### Short description (80 characters max)
```
Run your PG or hostel: rooms, beds, rent and residents in one app.
```
*(66 characters)*

### Full description (4000 characters max)

```
PGuru is PG and hostel management software built for owners in India.

Most PGs run on a register in a drawer, a WhatsApp group and a month-end evening
with a calculator. None of those tell you which bed is free tonight. PGuru does.

ROOMS AND BEDS
Branches, buildings, floors, rooms and individual beds. Every bed shows as
vacant, occupied, on notice or under maintenance, live, across every property
you run. Create rooms in bulk so setting up a 200-bed hostel is an evening
rather than a week.

RESIDENTS AND DOCUMENTS
Full profiles with stay history. Scan Aadhaar, PAN, passport, licence or voter
ID with the phone camera — images are compressed on the device before upload, so
it works on any connection. Document images sit behind a separate permission, so
within your own staff only the people you choose can view them.

RENT AND PAYMENTS
Set the rent once and the month runs itself. Invoices, part payments, dues and
digital receipts. UPI, cash and bank transfers all recorded the same way. Track
expenses and see profit and loss per branch.

A PORTAL FOR EVERY RESIDENT
Most PG software stops at the owner. Every resident here gets their own login —
they see their rent, download receipts, raise complaints, book laundry, check the
food menu and give checkout notice themselves. Fewer messages at eleven at night.

FILL YOUR EMPTY BEDS
Publish your free beds to the public search. People looking for a PG nearby find
you on a real map, see your photos and enquire directly. No broker, no
commission. Availability shows as a band such as "a few beds" — never an exact
count, so nobody can track your occupancy. Resident details are never published.

STAFF, ROLES AND CONTROL
A manager, a warden and an accountant should not see the same screens. Build the
roles you actually have, scope staff to the branches they work at, and see a full
audit log of who did what.

QR GATE ATTENDANCE
Residents mark entry and exit by scanning a QR at the gate, confirmed by
location so it cannot be done from elsewhere. Visitors and gate passes are
logged too.

WORKS EVERYWHERE
Web and Android. Nothing to install for residents — their portal opens in any
browser. Your data stays yours and can be exported at any time.

Built and maintained by Dygine Software Solutions.
Website: https://pgguru.in
```

### Category
**Business** *(secondary: Productivity)*

### Tags
PG management, hostel management, rent collection, property management,
tenant management, paying guest

### Contact details
- Email: `pgguru.in@gmail.com`
- Website: `https://pgguru.in`
- Privacy policy: `https://pgguru.in/privacy`

---

## 2. Graphics you still need to make

| Asset | Size | Notes |
|---|---|---|
| App icon | 512×512 PNG | From `frontend/public/pgguru-icon.png` |
| Feature graphic | 1024×500 PNG | Banner. Logo on the indigo #373DA6 background |
| Phone screenshots | min 2, ideally 4–8 | 16:9 or 9:16, min 320px |

**Screenshots to take**, in this order:
1. Owner dashboard — occupancy and collections
2. Bed grid — the vacant/occupied colours
3. Find PG — the map with a pin
4. Resident portal — My Rent

---

## 3. Data safety form — answer exactly this

This is the section that matters most. **Google cross-checks these answers
against what the app actually does at runtime.** A mismatch can get the app
removed after it is already published, so every line below was checked against
the source code rather than guessed.

### Does your app collect or share any of the required user data types?
**Yes**

### Is all of the user data collected by your app encrypted in transit?
**Yes** — everything is HTTPS.

### Do you provide a way for users to request that their data is deleted?
**Yes** — `https://pgguru.in/privacy` explains the route. Residents ask their PG;
account holders write to the contact address.

---

### Location

| Question | Answer |
|---|---|
| Approximate location | **Collected**, not shared |
| Precise location | **Collected**, not shared |
| Purpose | App functionality |
| Is it optional? | **Yes, users can choose** |
| Processed ephemerally? | **No** (gate attendance records are stored) |

*Why: the public search shows PGs near you, and gate attendance confirms a
resident is physically at the property. Read at the moment of the tap — there is
no background tracking.*

### Personal info

| Type | Collected | Shared | Purpose | Optional |
|---|---|---|---|---|
| Name | Yes | No | App functionality, Account management | No |
| Email address | Yes | No | App functionality, Account management | No |
| Phone number | Yes | No | App functionality | No |
| Address | Yes | No | App functionality | Yes |
| Other IDs | **Yes** | No | App functionality | Yes |

*"Other IDs" is the Aadhaar / PAN / passport document images. Declare it. It is
the single most important line on this form — an app that stores identity
documents and does not say so is the exact case Google removes apps for.*

### Photos and videos

| Type | Collected | Shared | Purpose | Optional |
|---|---|---|---|---|
| Photos | Yes | No | App functionality | Yes |

*Property photos on listings, and ID document scans.*

### Financial info

| Type | Collected | Shared | Purpose | Optional |
|---|---|---|---|---|
| Purchase history | Yes | No | App functionality | No |

*Rent and payment records entered by the PG. **Do not tick "Payment info"** —
card details are entered on Razorpay's own checkout and never reach this app or
its servers.*

### App activity

| Type | Collected | Shared | Purpose | Optional |
|---|---|---|---|---|
| App interactions | Yes | No | Analytics | No |

*The audit log records who did what inside a tenant.*

### Do NOT tick these

- Health and fitness
- Messages (SMS/email content)
- Contacts
- Calendar
- Files and docs *(the ID images are declared under Photos and Other IDs)*
- Web browsing history
- Device or other IDs for advertising

**Nothing is shared with third parties for advertising. Nothing is sold.**

---

## 4. Content rating questionnaire

- Category: **Utility, Productivity, Communication or Other**
- Violence, sexual content, profanity, drugs, gambling: **No** to all
- User-generated content shared publicly: **Yes** — PG listings and enquiries
- Does the app share user location with other users: **No**

Expected rating: **Everyone / 3+**

---

## 5. App access — important

Play reviewers cannot sign up for a PG account, so **you must give them
credentials or they will reject the app for being unreviewable.**

Under **App content → App access**, choose *All or some functionality is
restricted* and provide:

```
Login: an owner demo account email
Password: <create one before submitting>
Instructions: Sign in at the login screen. The dashboard, rooms, beds,
residents and rent screens are all reachable from the left navigation.
The public PG search at /find-pg needs no account.
```

**Create a real demo account with sample data before you submit.** Do not send
them a live PG's account.

---

## 6. The rejection risk, and the answer to it

Play rejects "webview-only" apps under its minimum functionality policy. This app
loads a website in a WebView, which is the pattern that policy targets.

Your defence, if it is rejected, is that the app uses genuine native device
functionality that a browser cannot:

- **Camera + ML Kit barcode scanning** — QR gate attendance and resident sign-in
- **Geolocation** — geofenced gate attendance and "PGs near me"
- **Local notifications**
- **Secure device storage** — Capacitor Preferences for the session token

Do not be surprised if the first submission bounces. It is common and appealable.

---

## 7. Release checklist

- [ ] Identity verification approved by Google
- [ ] Phone number verified
- [ ] App icon, feature graphic, 2+ screenshots uploaded
- [ ] Store listing pasted in
- [ ] Data safety form completed as above
- [ ] Content rating questionnaire done
- [ ] App access credentials provided
- [ ] Privacy policy URL entered
- [ ] AAB uploaded to Closed testing
- [ ] **20 testers added and opted in**
- [ ] 14 days of closed testing elapsed
- [ ] Promote to Production
