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

// ---- education (stage 1a) ----

export type Room = { id: string; branch_id: string; branch_name: string; name: string; capacity: number };

export type Course = {
  id: string;
  name: string;
  direction: string | null;
  default_price_month: string;
  duration_months: number;
  format: "offline" | "online";
};

export type Fill = { enrolled: number; capacity: number };

export type CohortRow = {
  id: string;
  code: string;
  course_id: string;
  course_name: string;
  branch_id: string;
  branch_name: string;
  instructor_id: string | null;
  instructor_name: string | null;
  room_id: string;
  room_name: string;
  start_date: string;
  end_date: string;
  weekdays: number[];
  start_time: string;
  end_time: string;
  capacity: number;
  price_month: string;
  status: string;
  fill: Fill;
};

export type LessonRow = {
  id: string;
  cohort_id: string;
  room_id: string;
  room_name: string;
  date: string;
  start: string;
  end: string;
  cancelled: boolean;
};

export type EnrollmentRow = {
  id: string;
  cohort_id: string;
  student_id: string;
  student_name: string;
  phone: string | null;
  status: string;
  enrolled_at: string;
};

export type StudentRow = {
  id: string;
  full_name: string;
  gender: "male" | "female" | null;
  phone: string | null;
  branch_id: string;
  branch_name: string;
  status: string;
  enrollments_count: number;
  created_at: string;
};

export type StudentDetail = StudentRow & {
  enrollments: {
    id: string;
    cohort_id: string;
    cohort_code: string;
    course_name: string;
    cohort_status: string;
    start_date: string;
    end_date: string;
    status: string;
    enrolled_at: string;
  }[];
};

export type GridLesson = {
  id: string;
  room_id: string;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  instructor_name: string | null;
  date: string;
  start: string;
  end: string;
};

export type ScheduleGrid = { date_from: string; date_to: string; rooms: Room[]; lessons: GridLesson[] };

export type EducationSummary = {
  active_cohorts: number;
  cohorts: Record<string, number>;
  students: Record<string, number>;
};
