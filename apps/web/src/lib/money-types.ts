// API shapes of the money screens (stage 2).
import type { Paged } from "./types";

/** Amounts arrive as strings («500.00») from lists and as numbers inside a 409's `current`. */
export type Money = string | number;

export type PaymentRow = {
  id: string;
  version: number;
  enrollment_id: string;
  student_id: string;
  student_name: string;
  phone: string | null;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  branch_id: string;
  branch_name: string;
  month_no: number;
  amount: Money;
  method: string;
  paid_at: string;
  status: string;
  confirmed_by_name: string | null;
  confirmed_at: string | null;
  note: string | null;
  created_at: string;
};

export type PaymentTotals = {
  confirmed: Money;
  pending: Money;
  confirmed_count: number;
  pending_count: number;
  count: number;
};

export type PaymentsPage = Paged<PaymentRow> & { summary: PaymentTotals };

export type DebtorRow = {
  enrollment_id: string;
  student_id: string;
  student_name: string;
  phone: string | null;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  branch_name: string;
  price_month: Money;
  months: number;
  paid: Money;
  paid_months: number[];
  expected: Money;
  debt: Money;
};

export type DebtorsPage = Paged<DebtorRow> & { total_debt: Money };

/** What the payment form picks from: a live enrollment with its price, months and what is paid. */
export type EnrollmentOption = {
  enrollment_id: string;
  student_name: string;
  phone: string | null;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  price_month: Money;
  months: number;
  next_month: number;
  paid: Money;
  paid_months: number[];
  expected: Money;
  debt: Money;
};

export type CohortPayments = {
  cohort_id: string;
  months: number;
  price_month: Money;
  enrolled: number;
  /** Enrolled students with a confirmed payment (#5: never more than `enrolled`). */
  payers: number;
  items: { enrollment_id: string; paid: Money; paid_months: number[]; expected: Money; debt: Money }[];
};

export type InstructorCard = {
  id: string;
  version: number;
  full_name: string;
  phone: string | null;
  branch_id: string | null;
  branch_name: string | null;
  is_active: boolean;
  default_rate: Money;
  cohorts: number;
  active_cohorts: number;
  students: number;
  income: Money;
  paid_out: Money;
};

export type InstructorDetail = InstructorCard & {
  cohorts_list: {
    id: string;
    version: number;
    code: string;
    course_name: string;
    status: string;
    start_date: string;
    end_date: string;
    rate: Money;
    students: number;
    income: Money;
  }[];
};

export type PayoutInfo = { id: string; version: number; amount: Money; paid_at: string; method: string; note: string | null };

export type SalaryRow = {
  instructor_id: string;
  instructor_name: string;
  cohort_id: string;
  cohort_version: number;
  cohort_code: string;
  course_name: string;
  branch_id: string;
  branch_name: string | null;
  /** First day of the month, `YYYY-MM-01`. */
  period: string;
  rate: Money;
  paid: Money;
  due: Money;
  state: string;
  payout: PayoutInfo | null;
};

export type SalarySummary = {
  month: string;
  fund_month: Money;
  total_schedule: Money;
  paid_total: Money;
  paid_month: Money;
  due_month: Money;
  overdue: Money;
};

export type SalaryData = { summary: SalarySummary; items: SalaryRow[]; total: number };

export type PayoutRow = {
  id: string;
  version: number;
  instructor_id: string;
  instructor_name: string;
  cohort_id: string;
  cohort_code: string;
  course_name: string;
  branch_name: string;
  period: string;
  amount: Money;
  rate: Money;
  paid_at: string;
  method: string;
  note: string | null;
};

export type PayoutsPage = Paged<PayoutRow> & { sum: Money };
