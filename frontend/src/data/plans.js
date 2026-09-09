export const PLANS = [
  {
    id: 'plan_starter', name: 'Starter', price: 1499, cycle: 'month', active: true,
    support: 'Email', color: 'slate',
    limits: { branches: 1, users: 5, beds: 60, customers: 60, storageGb: 2 },
    features: ['Rooms & beds', 'Residents', 'Rent & payments', 'Complaints', 'Basic reports'],
  },
  {
    id: 'plan_professional', name: 'Professional', price: 3999, cycle: 'month', active: true,
    support: 'Email + phone', color: 'brand', popular: true,
    limits: { branches: 3, users: 20, beds: 300, customers: 300, storageGb: 10 },
    features: ['Everything in Starter', 'Multi-branch', 'Custom roles', 'Attendance & QR gate', 'Food & laundry', 'Visitors & gate passes', 'Expense tracking'],
  },
  {
    id: 'plan_business', name: 'Business', price: 8999, cycle: 'month', active: true,
    support: 'Priority', color: 'emerald',
    limits: { branches: 10, users: 75, beds: 1200, customers: 1200, storageGb: 50 },
    features: ['Everything in Professional', 'Assets & inventory', 'Advanced reports', 'Audit log export', 'Announcement targeting'],
  },
  {
    id: 'plan_enterprise', name: 'Enterprise', price: 19999, cycle: 'month', active: true,
    support: 'Dedicated manager', color: 'violet',
    limits: { branches: 50, users: 400, beds: 8000, customers: 8000, storageGb: 250 },
    features: ['Everything in Business', 'Franchise grouping', 'API access', 'Custom SLA', 'Onboarding assistance'],
  },
]

export const planById = (id) => PLANS.find((p) => p.id === id)

export const LIMIT_LABELS = {
  branches: 'Branches', users: 'Users', beds: 'Beds',
  customers: 'Residents', storageGb: 'Storage',
}
