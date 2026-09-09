import {
  LayoutDashboard, Building2, Layers3, DoorOpen, BedDouble, Users, UserPlus, LogOut as CheckoutIcon,
  Repeat, ReceiptIndianRupee, Wallet, TrendingDown, MessageSquareWarning, UtensilsCrossed,
  WashingMachine, CalendarCheck, QrCode, UserCheck, TicketCheck, Megaphone, MessagesSquare,
  Package, Boxes, BarChart3, ScrollText, Settings, ShieldCheck, UsersRound, Building,
  CreditCard, Gauge, Home, Bell, User, Map,
} from 'lucide-react'

/**
 * Nav is DATA, not markup. Each item declares the permission it needs and the
 * sidebar/bottom bar filter themselves. Adding a module = adding a line here.
 */
export const ORG_NAV = [
  {
    group: 'Overview',
    items: [
      { label: 'Dashboard', to: '/app', icon: LayoutDashboard, perm: 'dashboard.view', end: true },
      { label: 'Reports', to: '/app/reports', icon: BarChart3, perm: 'reports.view' },
    ],
  },
  {
    group: 'Property',
    items: [
      { label: 'Branches', to: '/app/branches', icon: Building2, perm: 'branches.view' },
      { label: 'Floor plan', to: '/app/blueprint', icon: Map, perm: 'rooms.view' },
      { label: 'Buildings & floors', to: '/app/property', icon: Layers3, perm: 'property.view' },
      { label: 'Rooms', to: '/app/rooms', icon: DoorOpen, perm: 'rooms.view' },
      { label: 'Beds', to: '/app/beds', icon: BedDouble, perm: 'beds.view' },
    ],
  },
  {
    group: 'Residents',
    items: [
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
    ],
  },
  {
    group: 'Security',
    items: [
      { label: 'Visitors', to: '/app/visitors', icon: UserCheck, perm: 'visitors.view' },
      { label: 'Gate passes', to: '/app/gate-passes', icon: TicketCheck, perm: 'gatepass.view' },
    ],
  },
  {
    group: 'Communication',
    items: [
      { label: 'Announcements', to: '/app/announcements', icon: Megaphone, perm: 'announcements.view' },
      { label: 'Query centre', to: '/app/queries', icon: MessagesSquare, perm: 'queries.view' },
    ],
  },
  {
    group: 'Assets',
    items: [
      { label: 'Inventory', to: '/app/inventory', icon: Package, perm: 'inventory.view' },
      { label: 'Assets', to: '/app/assets', icon: Boxes, perm: 'assets.view' },
    ],
  },
  {
    group: 'Administration',
    items: [
      { label: 'Staff', to: '/app/staff', icon: UsersRound, perm: 'staff.view' },
      { label: 'Users', to: '/app/users', icon: Users, perm: 'users.view' },
      { label: 'Roles & permissions', to: '/app/roles', icon: ShieldCheck, perm: 'roles.view' },
      { label: 'Audit log', to: '/app/audit', icon: ScrollText, perm: 'audit.view' },
      { label: 'Settings', to: '/app/settings', icon: Settings, perm: 'settings.view' },
    ],
  },
]

export const MASTER_NAV = [
  {
    group: 'Platform',
    items: [
      { label: 'Dashboard', to: '/master', icon: LayoutDashboard, perm: 'master.dashboard', end: true },
      { label: 'Organisations', to: '/master/organizations', icon: Building, perm: 'master.organizations' },
      { label: 'Subscriptions', to: '/master/subscriptions', icon: CreditCard, perm: 'master.subscriptions' },
      { label: 'Usage monitoring', to: '/master/usage', icon: Gauge, perm: 'master.usage' },
    ],
  },
  {
    group: 'Governance',
    items: [
      { label: 'Platform audit log', to: '/master/audit', icon: ScrollText, perm: 'master.audit' },
      { label: 'Settings', to: '/master/settings', icon: Settings, perm: 'master.settings' },
    ],
  },
]

export const CUSTOMER_NAV = [
  {
    group: 'My stay',
    items: [
      { label: 'Home', to: '/me', icon: Home, end: true },
      { label: 'Rent & payments', to: '/me/rent', icon: ReceiptIndianRupee },
      { label: 'Food', to: '/me/food', icon: UtensilsCrossed },
      { label: 'Attendance', to: '/me/attendance', icon: CalendarCheck },
      { label: 'Laundry', to: '/me/laundry', icon: WashingMachine },
    ],
  },
  {
    group: 'Requests',
    items: [
      { label: 'Complaints', to: '/me/complaints', icon: MessageSquareWarning },
      { label: 'Visitors', to: '/me/visitors', icon: UserCheck },
      { label: 'Gate pass & leave', to: '/me/gate-pass', icon: TicketCheck },
      { label: 'Ask the PG', to: '/me/queries', icon: MessagesSquare },
    ],
  },
  {
    group: 'Account',
    items: [
      { label: 'Announcements', to: '/me/announcements', icon: Megaphone },
      { label: 'My profile', to: '/me/profile', icon: User },
    ],
  },
]

/** Phones get five destinations, chosen per portal. "More" opens the full drawer. */
export const BOTTOM_NAV = {
  master: [
    { label: 'Home', to: '/master', icon: LayoutDashboard, end: true },
    { label: 'PGs', to: '/master/organizations', icon: Building },
    { label: 'Plans', to: '/master/subscriptions', icon: CreditCard },
    { label: 'Usage', to: '/master/usage', icon: Gauge },
  ],
  org: [
    { label: 'Home', to: '/app', icon: LayoutDashboard, perm: 'dashboard.view', end: true },
    { label: 'Residents', to: '/app/residents', icon: Users, perm: 'customers.view' },
    { label: 'Rooms', to: '/app/blueprint', icon: Map, perm: 'rooms.view' },
    { label: 'Rent', to: '/app/invoices', icon: ReceiptIndianRupee, perm: 'invoices.view' },
  ],
  customer: [
    { label: 'Home', to: '/me', icon: Home, end: true },
    { label: 'Rent', to: '/me/rent', icon: ReceiptIndianRupee },
    { label: 'Scan', to: '/me/scan', icon: QrCode, primary: true },
    { label: 'Alerts', to: '/me/announcements', icon: Bell },
    { label: 'Profile', to: '/me/profile', icon: User },
  ],
}

export function filterNav(groups, can) {
  return groups
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.perm || can(i.perm)) }))
    .filter((g) => g.items.length)
}
