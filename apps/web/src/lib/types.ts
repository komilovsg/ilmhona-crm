import type { Level, Permissions } from "./permissions";

export type Me = {
  id: string;
  login: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  branch: { id: string; name: string } | null;
  role: { id: string; name: string; code: string | null };
  must_change_password: boolean;
  permissions: Permissions;
};

export type Branch = { id: string; name: string };

export type UserRow = {
  id: string;
  login: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  branch_id: string | null;
  branch_name: string | null;
  role_id: string;
  role_name: string;
  is_active: boolean;
  must_change_password: boolean;
  temp_password_expires_at: string | null;
  created_at: string;
};

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number };

export type RoleRow = {
  id: string;
  name: string;
  code: string | null;
  is_system: boolean;
  locked: boolean;
  permissions: Record<string, Level>;
  users_count: number;
};

export type SectionInfo = { key: string; label: string };

export type TempPassword = { user: UserRow; temp_password: string; expires_at?: string | null };

export type AuditRow = {
  id: number;
  at: string;
  user_id: string | null;
  user_name: string | null;
  user_login: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  diff: Record<string, unknown>;
};
