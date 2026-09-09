/**
 * "Staff" and "Users" are the same people.
 *
 * Before Phase 4 this screen read the seeded browser store while Users did not
 * exist. Now that staff accounts are real rows with real roles and branch
 * assignments, keeping a second screen backed by demo data would show two
 * different answers to the same question. Both nav entries render the live one.
 *
 * The nav keeps both entries because they carry different permissions
 * (staff.view vs users.view), so a role can be given the read-only path.
 */
export { default } from './Users'
