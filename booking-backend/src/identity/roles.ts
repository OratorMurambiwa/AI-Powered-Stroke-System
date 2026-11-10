export const roles = ['patient', 'doctor', 'technician', 'admin'] as const;
export type Role = typeof roles[number];
export function canonicalRole(value: unknown): Role | undefined {
  if (value === 'physician') return 'doctor';
  return roles.includes(value as Role) ? value as Role : undefined;
}
export const staffRoles = ['doctor', 'technician', 'admin'] as const;
