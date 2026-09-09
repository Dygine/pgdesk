/**
 * Single source of truth for the permission catalogue.
 * Every permission is "<module>.<action>". The UI, the nav and (in production)
 * the FastAPI dependency layer all read from this same list.
 */
export const PERMISSION_MODULES = [
  { key: 'dashboard',     label: 'Dashboard',      actions: ['view'] },
  { key: 'branches',      label: 'Branches',       actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'property',      label: 'Buildings & floors', actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'buildings',     label: 'Buildings',      actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'floors',        label: 'Floors',         actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'rooms',         label: 'Rooms',          actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'beds',          label: 'Beds',           actions: ['view', 'create', 'edit', 'delete', 'assign', 'transfer', 'block'] },
  { key: 'customers',     label: 'Residents',      actions: ['view', 'create', 'edit', 'delete', 'checkin', 'checkout', 'transfer', 'assign_bed', 'kyc_view', 'kyc_verify'] },
  { key: 'rent',          label: 'Rent',           actions: ['view', 'manage', 'generate'] },
  { key: 'invoices',      label: 'Rent & invoices', actions: ['view', 'create', 'edit', 'delete', 'cancel'] },
  { key: 'payments',      label: 'Payments',       actions: ['view', 'create', 'edit', 'delete', 'verify', 'refund'] },
  { key: 'expenses',      label: 'Expenses',       actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'complaints',    label: 'Complaints',     actions: ['view', 'create', 'assign', 'update', 'close', 'manage'] },
  { key: 'food',          label: 'Food & mess',    actions: ['view', 'manage', 'mark'] },
  { key: 'laundry',       label: 'Laundry',        actions: ['view', 'manage', 'book'] },
  { key: 'scan',          label: 'QR gate scan',   actions: ['view', 'manage'] },
  { key: 'attendance',    label: 'Attendance',     actions: ['view', 'manage', 'mark'] },
  { key: 'visitors',      label: 'Visitors',       actions: ['view', 'create', 'approve', 'manage'] },
  { key: 'gatepass',      label: 'Gate passes',    actions: ['view', 'create', 'approve', 'manage'] },
  { key: 'notifications', label: 'Notifications',  actions: ['view', 'manage'] },
  { key: 'announcements', label: 'Announcements',  actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'queries',       label: 'Query centre',   actions: ['view', 'create', 'respond', 'manage'] },
  { key: 'staff',         label: 'Staff',          actions: ['view', 'create', 'edit', 'deactivate'] },
  { key: 'inventory',     label: 'Inventory',      actions: ['view', 'create', 'manage', 'adjust'] },
  { key: 'assets',        label: 'Assets',         actions: ['view', 'create', 'manage'] },
  { key: 'reports',       label: 'Reports',        actions: ['view', 'export'] },
  { key: 'audit',         label: 'Audit log',      actions: ['view', 'export'] },
  { key: 'users',         label: 'Users',          actions: ['view', 'create', 'edit', 'deactivate'] },
  { key: 'roles',         label: 'Roles',          actions: ['view', 'create', 'edit', 'delete'] },
  { key: 'settings',      label: 'Settings',       actions: ['view', 'manage'] },
]

export const ACTION_LABELS = {
  view: 'View', create: 'Create', edit: 'Edit', delete: 'Delete',
  assign: 'Assign', transfer: 'Transfer', block: 'Block',
  checkin: 'Check in', checkout: 'Check out',
  approve: 'Approve', refund: 'Refund', waive: 'Waive',
  update: 'Update', close: 'Close', publish: 'Publish',
  mark: 'Mark', manage: 'Manage', reply: 'Reply',
  deactivate: 'Deactivate', export: 'Export',
}

export const ALL_PERMISSIONS = PERMISSION_MODULES.flatMap((m) =>
  m.actions.map((a) => `${m.key}.${a}`)
)

/** Master-admin permissions live in a separate namespace — they never touch tenant data. */
export const MASTER_PERMISSIONS = [
  'master.dashboard', 'master.organizations', 'master.organizations.create',
  'master.organizations.edit', 'master.subscriptions', 'master.usage',
  'master.audit', 'master.impersonate', 'master.settings',
]

export const permsFor = (moduleKey, actions) => actions.map((a) => `${moduleKey}.${a}`)
