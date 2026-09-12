# PGuru — friendliness review

You asked me to make the tool less likely to draw client complaints and to
"minimise" where possible. Here's what I did and what I recommend.

## What I already changed (client-facing, safe, done in this zip)

The first thing a client touches is the **download + install funnel** on
get.dygine.com — and that's exactly where "old app / can't download / confusing"
lives. So I fixed that end to end:

- **Steered non-technical users to the zero-install path.** The web version
  (pgguru.in) needs no download, no "unknown sources", no sideloading — it
  works on any phone including iPhone. The page now says so plainly and points to
  "Add to Home screen" for an app-style icon. Fewer clients get stuck in the
  sideload warnings, fewer support calls.
- **Killed the update confusion.** Added a note: once the app is installed you
  never re-download it for updates — it refreshes itself. (This was confusing you
  too.)
- **Fixed the stale-download cache** so the *next* new APK actually reaches phones
  (see `APK-DOWNLOAD-FIX.md`).

## The single biggest in-app friendliness issue

**The office menu is a wall of 9 groups and ~32 links, all expanded.** For a small
PG owner this is the "too complicated" feeling. The phone bottom bar is already
trimmed to 4 + More (good), but the drawer/sidebar is dense.

I did **not** auto-edit this, because I can't run the full app here to prove I
didn't break a working screen, and you deliberately tuned this menu recently. But
it's one data file (`frontend/src/nav/navConfig.js`) and the change is low-risk and
trivially reversible. Here's a ready-to-paste replacement that collapses it from
**9 groups to 6** — Security folds into Operations, and Communication + Assets +
Administration fold into one "Admin & setup" bucket at the bottom. Nothing else in
the file changes (`MASTER_NAV`, `CUSTOMER_NAV`, `BOTTOM_NAV`, `filterNav`, the icon
import line all stay as they are). Say the word and I'll drop it into the zip.

```js
export const ORG_NAV = [
  {
    group: 'Overview',
    items: [
      { label: 'Dashboard', to: '/app', icon: LayoutDashboard, perm: 'dashboard.view', end: true },
      { label: 'Floor plan', to: '/app/blueprint', icon: Map, perm: 'rooms.view' },
      { label: 'Reports', to: '/app/reports', icon: BarChart3, perm: 'reports.view' },
    ],
  },
  {
    group: 'Property',
    items: [
      { label: 'Branches', to: '/app/branches', icon: Building2, perm: 'branches.view' },
      { label: 'Buildings & floors', to: '/app/property', icon: Layers3, perm: 'property.view' },
      { label: 'Rooms', to: '/app/rooms', icon: DoorOpen, perm: 'rooms.view' },
      { label: 'Beds', to: '/app/beds', icon: BedDouble, perm: 'beds.view' },
    ],
  },
  {
    group: 'Residents',
    items: [
      { label: 'Enquiries', to: '/app/enquiries', icon: Inbox, perm: 'customers.view' },
      { label: 'All residents', to: '/app/residents', icon: Users, perm: 'customers.view' },
      { label: 'Check-in', to: '/app/check-in', icon: UserPlus, perm: 'customers.checkin' },
      { label: 'Room transfer', to: '/app/transfer', icon: Repeat, perm: 'customers.transfer' },
      { label: 'Checkout', to: '/app/checkout', icon: CheckoutIcon, perm: 'customers.checkout' },
    ],
  },
  {
    group: 'Finance',
    items: [
      { label: 'Rent & invoices', to: '/app/invoices', icon: ReceiptIndianRupee, perm: 'invoices.view' },
      { label: 'Payments', to: '/app/payments', icon: Wallet, perm: 'payments.view' },
      { label: 'Expenses', to: '/app/expenses', icon: TrendingDown, perm: 'expenses.view' },
      { label: 'Accounts (P&L)', to: '/app/accounts', icon: Scale, perm: 'reports.view' },
    ],
  },
  {
    group: 'Operations',
    items: [
      { label: 'Complaints', to: '/app/complaints', icon: MessageSquareWarning, perm: 'complaints.view' },
      { label: 'Attendance', to: '/app/attendance', icon: CalendarCheck, perm: 'attendance.view' },
      { label: 'Gate scan', to: '/app/scan', icon: QrCode, perm: 'attendance.mark' },
      { label: 'Food & mess', to: '/app/food', icon: UtensilsCrossed, perm: 'food.view' },
      { label: 'Laundry', to: '/app/laundry', icon: WashingMachine, perm: 'laundry.view' },
      { label: 'Visitors', to: '/app/visitors', icon: UserCheck, perm: 'visitors.view' },
      { label: 'Gate passes', to: '/app/gate-passes', icon: TicketCheck, perm: 'gatepass.view' },
    ],
  },
  {
    group: 'Admin & setup',
    items: [
      { label: 'Announcements', to: '/app/announcements', icon: Megaphone, perm: 'announcements.view' },
      { label: 'Query centre', to: '/app/queries', icon: MessagesSquare, perm: 'queries.view' },
      { label: 'Inventory', to: '/app/inventory', icon: Package, perm: 'inventory.view' },
      { label: 'Assets', to: '/app/assets', icon: Boxes, perm: 'assets.view' },
      { label: 'Staff', to: '/app/staff', icon: UsersRound, perm: 'staff.view' },
      { label: 'Users & logins', to: '/app/users', icon: KeyRound, perm: 'users.view' },
      { label: 'Roles & permissions', to: '/app/roles', icon: ShieldCheck, perm: 'roles.view' },
      { label: 'Audit log', to: '/app/audit', icon: ScrollText, perm: 'audit.view' },
      { label: 'Settings', to: '/app/settings', icon: Settings, perm: 'settings.view' },
    ],
  },
]
```

A heavier alternative (more work, better long-term) is to make the sidebar groups
**collapsible** and remember which are open, in `components/layout/AppShell.jsx`.
That keeps all 9 groups but shows one at a time. I can build that if you'd rather.

## Other friction worth fixing — pick and I'll apply

Ranked by how much a client would feel it. I've left these as proposals rather than
guessing, because each needs a look at the live screen to change safely:

1. **First-run is empty and unguided.** A new owner logs in to empty branches,
   rooms, beds and residents with no "start here". A short dashboard checklist
   (Add a branch → Add rooms → Add beds → Add your first resident, ticking off as
   each is done) removes most "what do I do now" confusion. I can build this.
2. **Data tables on a phone.** Residents / Invoices / Payments are table-heavy; on a
   380px screen tables get cramped. If they aren't already switching to stacked
   cards on mobile, that's a common complaint. Tell me which pages feel worst and
   I'll card-ify them.
3. **Sideload anxiety.** Covered on the landing page now, but you could also show a
   one-line "Add to Home screen" hint inside the web app on first visit.
4. **Label consistency.** The office calls it "Query centre"; residents see "Ask the
   PG" — same feature, two names. Fine if intended, worth aligning if not. Minor.

## On file/app size — leave it alone

The 30 MB APK is normal for a Capacitor app and isn't a "bloat" problem worth
chasing. With `server.url` set, most of that is the offline fallback bundle; trying
to strip it to shave megabytes would remove the offline screen for little benefit.
Not recommended.

---

**Why I didn't just rewrite everything and hand it back "made friendly":** the app
is 83 screens and I can't run it here to verify a change didn't break a working
flow — shipping that blind would be exactly the kind of thing that turns into new
bugs. The download funnel I *could* verify, so that's done. For the in-app items,
point me at the ones you want and I'll implement them properly.
