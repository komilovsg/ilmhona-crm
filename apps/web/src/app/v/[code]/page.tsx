import { CodeForm } from "../CodeForm";

import { checkCertificate } from "@/lib/verify-server";
import { STATUS_TEXT, formatDay, studyPeriod, type PublicCertificate } from "@/lib/verify";

export const dynamic = "force-dynamic";

const TONE = {
  valid: { box: "bg-success-50 text-success-800 ring-success-200 dark:text-success-700", dot: "bg-success-600" },
  revoked: { box: "bg-danger-50 text-danger-800 ring-danger-200 dark:text-danger-700", dot: "bg-danger-600" },
  replaced: { box: "bg-warning-50 text-warning-800 ring-warning-200 dark:text-warning-700", dot: "bg-warning-600" },
} as const;

function Mark({ status }: { status: PublicCertificate["status"] }) {
  return (
    <svg aria-hidden="true" className="h-5 w-5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} viewBox="0 0 24 24">
      {status === "valid" ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M7 7l10 10M17 7L7 17" />}
    </svg>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-1 gap-0.5 py-3 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-sm text-default-500">{label}</dt>
      <dd className="min-w-0 break-words font-medium">{value}</dd>
    </div>
  );
}

function Found({ cert }: { cert: PublicCertificate }) {
  const tone = TONE[cert.status];
  const text = STATUS_TEXT[cert.status];
  const period = studyPeriod(cert);
  return (
    <article className="overflow-hidden rounded-2xl bg-content1 shadow-[var(--lift)]">
      <div className={`flex items-start gap-3 p-5 ring-1 ring-inset sm:p-6 ${tone.box}`} role="status">
        <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white ${tone.dot}`}>
          <Mark status={cert.status} />
        </span>
        <div className="min-w-0">
          <p className="font-display text-xl font-semibold leading-tight">{text.title}</p>
          <p className="mt-1 text-sm">{text.note(cert)}</p>
        </div>
      </div>
      <dl className="divide-y divide-divider px-5 sm:px-6">
        <Row label="Владелец" value={cert.holder} />
        <Row label="Курс" value={cert.course} />
        {period && <Row label="Обучение" value={period} />}
        <Row label="Номер" value={cert.number} />
        <Row label="Дата выдачи" value={formatDay(cert.issued_on)} />
        <Row label="Выдал" value={cert.issuer} />
      </dl>
    </article>
  );
}

function Notice({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl bg-content1 p-5 shadow-[var(--lift)] sm:p-6" role="status">
      <p className="font-display text-xl font-semibold">{title}</p>
      <p className="mt-1 text-default-500">{text}</p>
    </div>
  );
}

export default async function VerifyPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const result = await checkCertificate(decodeURIComponent(code));
  return (
    <>
      <h1 className="mb-6 font-display text-2xl font-semibold tracking-tight sm:text-3xl">Проверка сертификата</h1>
      {result.kind === "found" && <Found cert={result.cert} />}
      {result.kind === "not_found" && (
        <Notice text="Проверьте код: он напечатан под QR-кодом на сертификате. Если код верный, свяжитесь с ilmhona." title="Сертификат не найден" />
      )}
      {result.kind === "limit" && <Notice text="Слишком много проверок подряд. Попробуйте через минуту." title="Подождите минуту" />}
      {result.kind === "error" && <Notice text="Сервис проверки временно недоступен. Попробуйте позже." title="Не удалось проверить" />}
      <div className="mt-6">
        <CodeForm title="Проверить другой сертификат" />
      </div>
    </>
  );
}
