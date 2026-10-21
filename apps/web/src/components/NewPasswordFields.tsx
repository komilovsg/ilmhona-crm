"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";

import { Icon } from "@/components/Icon";
import { PasswordField } from "@/components/PasswordField";
import { api } from "@/lib/api";
import { canSubmit, checkRules, strengthOf, type PasswordPolicy, type RuleState } from "@/lib/password";

/** The rules come from the API, one source with the backend check. */
export function usePasswordPolicy() {
  return useQuery({
    queryKey: ["password-policy"],
    queryFn: () => api<PasswordPolicy>("/api/v1/auth/password-policy"),
    staleTime: Infinity,
  });
}

/** Rule states and whether the form may be submitted (all rules pass and the confirm matches). */
export function usePasswordRules(next: string, repeat: string, login: string, current: string) {
  const { data: policy } = usePasswordPolicy();
  const rules: RuleState[] = policy ? checkRules(next, policy, login, current) : [];
  return { rules, valid: !!policy && canSubmit(rules, next, repeat) };
}

const METER = ["bg-danger", "bg-warning", "bg-success"];

/** New password + live checklist + strength meter + confirm. Colour is never the only signal:
 *  every rule has a ✓ / • icon and its text, the meter has a word. */
export function NewPasswordFields({
  next,
  repeat,
  rules,
  onNext,
  onRepeat,
}: {
  next: string;
  repeat: string;
  rules: RuleState[];
  onNext: (v: string) => void;
  onRepeat: (v: string) => void;
}) {
  const strength = strengthOf(next);
  const mismatch = repeat !== "" && repeat !== next;

  return (
    <>
      <PasswordField autoComplete="new-password" label="Новый пароль" value={next} onValueChange={onNext} />
      <div className="space-y-2">
        <ul aria-live="polite" className="space-y-1 text-sm">
          {rules.map((r) => (
            <li key={r.id} className={clsx("flex items-center gap-2", r.ok ? "text-success-700 dark:text-success" : "text-default-500")}>
              <span aria-hidden className="flex w-4 justify-center">
                {r.ok ? <Icon name="check" size={14} /> : "•"}
              </span>
              <span>
                {r.label}
                <span className="sr-only">{r.ok ? ": выполнено" : ": не выполнено"}</span>
              </span>
            </li>
          ))}
        </ul>
        {strength.level > 0 && (
          <div className="flex items-center gap-2 text-xs" aria-live="polite">
            <div aria-hidden className="flex flex-1 gap-1">
              {[1, 2, 3].map((i) => (
                <span key={i} className={clsx("h-1.5 flex-1 rounded-full", i <= strength.level ? METER[strength.level - 1] : "bg-default-200")} />
              ))}
            </div>
            <span className="text-default-600">Надёжность: {strength.label}</span>
          </div>
        )}
      </div>
      <PasswordField autoComplete="new-password" label="Повторите новый пароль" value={repeat} onValueChange={onRepeat} />
      {repeat !== "" && (
        <p aria-live="polite" className={clsx("text-sm", mismatch ? "text-danger" : "text-success-700 dark:text-success")}>
          {mismatch ? "не совпадает" : "✓ совпадает"}
        </p>
      )}
    </>
  );
}
