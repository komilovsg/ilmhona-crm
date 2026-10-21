/** Password checklist logic. The rules (ids, labels, length bounds) come from the API
 *  (`GET /auth/password-policy`, backend `app/core/password_policy.py`); only how each id is
 *  checked lives here. */

export type PasswordPolicy = {
  min_length: number;
  max_length: number;
  rules: { id: string; label: string }[];
};

export type RuleState = { id: string; label: string; ok: boolean };

const LETTER = /\p{L}/u;
const DIGIT = /\d/;

function passes(id: string, password: string, policy: PasswordPolicy, login: string, current: string): boolean {
  switch (id) {
    case "length":
      return password.length >= policy.min_length && password.length <= policy.max_length;
    case "letter":
      return LETTER.test(password);
    case "digit":
      return DIGIT.test(password);
    case "not_login":
      return password !== "" && password.toLowerCase() !== login.toLowerCase();
    case "not_current":
      return password !== "" && password !== current;
    default:
      return true; // a rule this build does not know: the server still enforces it
  }
}

export function checkRules(password: string, policy: PasswordPolicy, login: string, current: string): RuleState[] {
  return policy.rules.map((r) => ({
    id: r.id,
    label: r.label,
    // an empty field has passed nothing yet, even a negative rule
    ok: password !== "" && passes(r.id, password, policy, login, current),
  }));
}

export type Strength = { level: 0 | 1 | 2 | 3; label: string };

/** Simple heuristic: length plus character classes. 0 = nothing typed. */
export function strengthOf(password: string): Strength {
  if (!password) return { level: 0, label: "" };
  const classes = [/\p{Ll}/u, /\p{Lu}/u, /\d/, /[^\p{L}\d]/u].filter((re) => re.test(password)).length;
  const score = (password.length >= 10 ? 1 : 0) + (password.length >= 12 ? 1 : 0) + (classes >= 3 ? 1 : 0) + (classes >= 4 ? 1 : 0);
  if (score <= 1) return { level: 1, label: "слабый" };
  if (score <= 2) return { level: 2, label: "средний" };
  return { level: 3, label: "надёжный" };
}

export function canSubmit(rules: RuleState[], password: string, repeat: string): boolean {
  return rules.every((r) => r.ok) && password === repeat;
}
