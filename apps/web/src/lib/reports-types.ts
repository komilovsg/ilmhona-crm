// API shapes of the report screens (stage 4).

export type LeadItem = {
  id: string;
  full_name: string;
  phone: string | null;
  status: string;
  course_name: string | null;
  created_at: string;
  next_contact_at: string | null;
};

export type Overview = {
  leads: number;
  conversion: number;
  funnel: Record<string, number>;
  active_students: number;
  students_total: number;
  // money is null without the section it comes from (payments / instructors / marketing)
  income: string | null;
  active_cohorts: number;
  recruiting_cohorts: number;
  cohorts_total: number;
  payroll: string | null;
  profit: string | null;
  ads: string | null;
  campaigns: number;
  graduates: number;
  converted: number;
  cac: string | null;
  unfilled: {
    count: number;
    items: {
      lesson_id: string;
      cohort_id: string;
      cohort_code: string;
      course_name: string;
      date: string;
      marked: number;
      total: number;
    }[];
  };
  callbacks: { count: number; items: LeadItem[] };
  recent_leads: LeadItem[];
};

export type MonthRow = {
  month: string;
  income: string | null;
  payroll: string | null;
  ads: string | null;
  profit: string | null;
  new_students: number;
  leads: number;
};

export type CourseRow = {
  course_id: string;
  course_name: string;
  cohorts: number;
  income: string | null;
  students: number;
  graduates: number;
};

export type MasterRow = {
  cohort_id: string;
  code: string;
  branch_name: string;
  start_date: string;
  end_date: string;
  course_name: string;
  format: string;
  price_month: string;
  status: string;
  leads: number;
  zero_lesson: number;
  enrolled: number;
  paid_1: number;
  paid_2: number;
  paid_3: number;
  income: string | null;
  ltv: string | null;
  graduates: number;
  employed: number;
};

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number };

export type GraduateRow = {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  phone: string | null;
  branch_name: string;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  instructor_name: string | null;
  enrolled_at: string;
  score: number;
  /** The total came from the old system (no homework / final): shown as such. */
  score_legacy: boolean;
  paid: string | null;
  certificate_no: string | null;
  employed: boolean;
  organization: string | null;
};

export type GraduateCourseRow = {
  course_id: string;
  course_name: string;
  graduates: number;
  avg_score: number;
  employed: number;
  employed_percent: number;
};

export type EmploymentRow = {
  id: string;
  version: number;
  student_id: string;
  student_name: string;
  phone: string | null;
  branch_name: string;
  enrollment_id: string | null;
  cohort_code: string | null;
  course_name: string | null;
  organization: string;
  position: string | null;
  employed_at: string;
};
