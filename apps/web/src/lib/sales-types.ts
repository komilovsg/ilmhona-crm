// API shapes of the sales screens (stage 3).

export type DuplicateRef = { id: string; full_name: string };
export type Duplicates = {
  leads: (DuplicateRef & { status: string; created_at: string })[];
  students: DuplicateRef[];
};

export type LeadRow = {
  id: string;
  version: number;
  full_name: string;
  raw_name: string | null;
  phone: string | null;
  phone_raw: string | null;
  course_id: string | null;
  course_name: string | null;
  source: string;
  campaign_id: string | null;
  campaign_name: string | null;
  branch_id: string;
  branch_name: string;
  call_status: string;
  next_contact_at: string | null;
  status: string;
  refusal_reason: string | null;
  comment: string | null;
  needs_review: boolean;
  converted_student_id: string | null;
  created_at: string;
  /** Set by create / phone edit: people with the same phone (a warning, not a block). */
  duplicates?: Duplicates | null;
};

export type LeadFunnel = {
  counts: Record<string, number>;
  conversion: number;
  callbacks_today: number;
  needs_review: number;
};

export type ConvertResult = {
  lead: LeadRow;
  student: { id: string; full_name: string; created: boolean };
  enrollment: { id: string; cohort_id: string; cohort_code: string; new: boolean } | null;
  already: boolean;
};

export type CampaignRow = {
  id: string;
  version: number;
  name: string;
  course_id: string | null;
  course_name: string | null;
  branch_id: string;
  branch_name: string;
  platform: string;
  start_date: string;
  end_date: string | null;
  budget: string;
  status: string;
  leads: number;
  converted: number;
  enrolled: number;
  cpl: string | null;
  cac: string | null;
};

export type CampaignTotals = {
  campaigns: number;
  budget: string;
  leads: number;
  converted: number;
  enrolled: number;
  cpl: string | null;
  cac: string | null;
};

export type CampaignList = { items: CampaignRow[]; totals: CampaignTotals };

export type ImportRow = {
  line: number;
  full_name: string;
  raw_name: string | null;
  phone: string | null;
  source: string;
  needs_review: boolean;
  skip: string | null;
  duplicates: { kind: "lead" | "student" | "file"; id?: string; full_name?: string; line?: number }[];
};

export type ImportPreview = {
  headers: string[];
  mapping: Record<string, string | null>;
  rows: ImportRow[];
  truncated: boolean;
  totals: { rows: number; importable: number; skipped: number; needs_review: number; duplicates: number };
};
