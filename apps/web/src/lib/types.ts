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
  /** «Ведёт занятия»: may be a cohort's instructor, whatever the role. */
  teaches: boolean;
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
  teaches: boolean;
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

export type Room = {
  id: string;
  version: number;
  branch_id: string;
  branch_name: string;
  name: string;
  capacity: number;
  archived: boolean;
  archived_at: string | null;
};

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

export type Funding = "платный" | "бесплатный" | "донор" | "смешанный";
export type DonorRef = { id: string; name: string; archived: boolean };
export type Seats = { paying: number; donor: number; free: number };

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
  /** платный | бесплатный | донор | смешанный */
  funding: Funding;
  donors: DonorRef[];
  /** enrolled students who pay / are paid for by a donor / study free */
  seats: Seats;
  status: string;
  /** «Срок вышел»: активный after the end date, not finished by hand */
  overdue: boolean;
  /** no marks for a long time: the idle days and the date the nightly job closes the cohort */
  stale: { idle_days: number; closes_on: string | null } | null;
  fill: Fill;
  /** list only, for those who see payments: confirmed payers and income (Decimal as string) */
  payers?: number;
  income?: string;
  /** detail only: lessons that came overlapping another lesson of the instructor (old data) */
  instructor_conflicts?: number;
  /** detail only: enrollments with an issued certificate (a finished cohort with any cannot be reopened) */
  certificates_issued?: number;
};

export type FinishItem = { enrollment_id: string; student_id: string; student_name: string };
export type FinishPreview = {
  graduates: number;
  completed: number;
  excluded_count: number;
  overdue: boolean;
  /** lessons after today with no marks: the finish cancels them and frees the room */
  lessons_to_free: number;
  /** debt of the cohort (only for who sees payments): a finish keeps it in «Должники» */
  debtors?: number;
  debt?: string;
  lists: {
    graduates: FinishItem[];
    completed: FinishItem[];
    excluded: (FinishItem & { status: string })[];
  };
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
  /** the donor that pays for the student; null = pays themself (or a free cohort) */
  donor_id: string | null;
  /** «Не платит»: studies for free in a paid or mixed cohort (no donor); owes nothing */
  not_paying: boolean;
  /** moved from a donor or «не платит» to paying themself then: the debt counts from that month */
  pays_from: string | null;
  /** hints for the instructor: they added it, and it has no payments, marks or grades */
  created_by_me: boolean;
  deletable: boolean;
  /** set by the create response when this enrollment took the cohort over its seats */
  over_capacity?: Fill | null;
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
  /** First lesson after today in scope, null when none is scheduled. */
  next_lesson: LessonItem | null;
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
  excused?: boolean;
  reason: string | null;
  marked_at: string | null;
  marked_by: string | null;
};

export type LessonAttendance = {
  lesson: {
    id: string;
    cohort_id: string;
    cohort_code: string;
    cohort_start: string;
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
  /** enrolled after this lesson: not markable until their enrollment day moves */
  late: { enrollment_id: string; version: number; student_name: string; enrolled_on: string }[];
  marked: number;
  total: number;
};

export type AttendanceStats = {
  /** lessons held minus the excused ones */
  held: number;
  present: number;
  absent: number;
  excused: number;
  unmarked: number;
  /** present / held, null while nothing is held yet */
  percent: number | null;
  /** 0..20 */
  score: number;
};

export type GridLessonCol = { id: string; date: string; start: string; end: string; cancelled: boolean; held: boolean; writable: boolean };

export type GridStudent = AttendanceStats & {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  status: string;
  version: number;
  enrolled_at: string;
  enrolled_on: string;
  marks: Record<string, { present: boolean; excused?: boolean; reason: string | null }>;
};

export type AttendanceGrid = { cohort_id: string; cohort_code: string; start_date: string; lessons: GridLessonCol[]; students: GridStudent[] };

export type GradeRow = {
  enrollment_id: string;
  version: number;
  student_id: string;
  student_name: string;
  status: string;
  /** Entered points by category key (archived categories included). */
  scores: Record<string, number>;
  /** Counted points by category key of the cohort's scheme. */
  points: Record<string, number>;
  attendance_score: number;
  total: number;
  /** The total scaled up from the categories that already count; null = nothing yet. */
  projected: number | null;
  passed: boolean;
  held: number;
  present: number;
  unmarked: number;
  percent: number | null;
};

export type GradesData = {
  scheme: {
    source: "standard" | "cohort";
    pass_score: number;
    categories: { key: string; name: string; weight: number; kind: "attendance" | "manual" }[];
  };
  rows: GradeRow[];
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
