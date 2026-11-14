import clsx from "clsx";

import { Icon } from "./Icon";

import { telHref } from "@/lib/format";
import { whatsappHref } from "@/lib/sales";

/** «Позвонить» (tel:) and WhatsApp (wa.me) of a person, like on the lead cards. */
export function ContactButtons({ phone, compact }: { phone: string | null; compact?: boolean }) {
  if (!phone) return null;
  const wa = whatsappHref(phone);
  const base = clsx("inline-flex items-center justify-center gap-1.5 rounded-xl font-medium", compact ? "h-8 px-2.5 text-xs" : "h-10 px-4 text-sm");

  return (
    <>
      <a aria-label={`Позвонить ${phone}`} className={clsx(base, "bg-primary/10 text-brand-text")} href={telHref(phone)}>
        <Icon name="phone" size={compact ? 14 : 18} />
        {!compact && "Позвонить"}
      </a>
      {wa && (
        <a aria-label="WhatsApp" className={clsx(base, "bg-success/15 text-success-700 dark:text-success")} href={wa} rel="noreferrer" target="_blank">
          <Icon name="message" size={compact ? 14 : 18} />
          {!compact && "WhatsApp"}
        </a>
      )}
    </>
  );
}
