import type { Level, Permissions } from "./permissions";

export type Me = {
  version: number;
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
  version: number;
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
  version: number;
  id: string;
  name: string;
  code: string | null;
  is_system: boolean;
  locked: boolean;
  permissions: Record<string, Level>;
  users_count: number;
  /** The current user may give this role to someone (list endpoint only). */
  assignable?: boolean;
};

export type SectionInfo = { key: string; label: string };

export type TempPassword = { user: UserRow; temp_password: string; expires_at?: string | null };

export type AuditRow = {
  id: number;
  at: string;
  user_id: string | null;
  user_name: string | null;
  user_login: string | null;
  branch_name: string | null;
  action: string;
  section: string | null;
  entity: string;
  entity_id: string | null;
  /** The entry as a Russian sentence, written by the API. */
  text: string;
  /** The page it leads to; null when the entity is gone or out of reach. */
  link: { entity: string; id: string } | null;
  diff: Record<string, unknown>;
};

// ---- education (stage 1a) ----

export type Room = { id: string; version: number; branch_id: string; branch_name: string; name: string; capacity: number };

export type Course = {
  version: number;
  id: string;
  name: string;
  direction: string | null;
  default_price_month: string;
  duration_months: number;
  format: "offline" | "online";
};

export type Fill = { enrolled: number; capacity: number };

export type CohortRow = {
  version: number;
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
  /** detail only: lessons that came overlapping another lesson of the instructor (old data) */
  instructor_conflicts?: number;
};

export type LessonRow = {
  version: number;
  id: string;
  cohort_id: string;
  room_id: string;
  room_name: string;
  date: string;
  start: string;
  end: string;
  cancelled: boolean;
  instructor_conflict?: boolean;
};

export type EnrollmentRow = {
  version: number;
  id: string;
  cohort_id: string;
  student_id: string;
  student_name: string;
  phone: string | null;
  status: string;
  enrolled_at: string;
  needs_review: boolean;
  review_reason: string | null;
};

export type StudentRow = {
  version: number;
  id: string;
  full_name: string;
  gender: "male" | "female" | null;
  phone: string | null;
  branch_id: string;
  branch_name: string;
  status: string;
  enrollments_count: number;
  created_at: string;
  needs_review: boolean;
  review_reason: string | null;
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
    needs_review: boolean;
    review_reason: string | null;
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

export type AuditPage = Paged<AuditRow> & {
  /** id -> display name of the users, roles and branches the page mentions. */
  names: Record<string, string>;
  /** section key -> Russian label */
  sections: Record<string, string>;
};

// ---- attendance and grades (stage 1b) ----

/** A lesson with how many of its students are marked (`marked` / `total`). */
export type LessonItem = {
  lesson_id: string;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  room_name: string;
  date: string;
  start: string;
  end: string;
  marked: number;
  total: number;
  instructor_id: string | null;
  instructor_name: string | null;
};

export type TodayData = {
  date: string;
  today: LessonItem[];
  /** Held lessons of the last 30 days with somebody still unmarked (#21). */
  unfilled: LessonItem[];
  unfilled_by_instructor: { instructor_id: string | null; instructor_name: string | null; lessons: LessonItem[] }[];
};

export type MarkRow = {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  status: string;
  /** null = not marked yet */
  present: boolean | null;
  reason: string | null;
  marked_at: string | null;
  marked_by: string | null;
};

export type LessonAttendance = {
  lesson: {
    id: string;
    cohort_id: string;
    cohort_code: string;
    course_name: string;
    room_name: string;
    date: string;
    start: string;
    end: string;
    cancelled: boolean;
    held: boolean;
    number: number | null;
    of: number;
  };
  prev_id: string | null;
  next_id: string | null;
  students: MarkRow[];
  marked: number;
  total: number;
};

export type AttendanceStats = {
  held: number;
  present: number;
  absent: number;
  unmarked: number;
  /** present / held, null while nothing is held yet */
  percent: number | null;
  /** 0..20 */
  score: number;
};

export type GridLessonCol = { id: string; date: string; start: string; end: string; cancelled: boolean; held: boolean };

export type GridStudent = AttendanceStats & {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  status: string;
  enrolled_at: string;
  marks: Record<string, { present: boolean; reason: string | null }>;
};

export type AttendanceGrid = { cohort_id: string; cohort_code: string; lessons: GridLessonCol[]; students: GridStudent[] };

export type GradeRow = {
  enrollment_id: string;
  version: number;
  student_id: string;
  student_name: string;
  status: string;
  homework: number | null;
  final: number | null;
  attendance_score: number;
  total: number;
  passed: boolean;
  held: number;
  present: number;
  unmarked: number;
  percent: number | null;
};

export type SessionRow = {
  id: string;
  device: string;
  created_at: string;
  last_used_at: string;
  remember: boolean;
  current: boolean;
};

export type ResetRequestRow = {
  id: string;
  user_id: string;
  login: string;
  full_name: string;
  role_name: string;
  created_at: string;
};
