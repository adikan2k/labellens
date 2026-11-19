/**
 * My preferences (DESIGN.md, "My preferences"): someone's own rules, kept in this browser only,
 * and whether a product meets them. Every rule is optional and starts empty; nothing here
 * suggests a value. Missing data is "unknown", never a pass.
 */
import type { Additive, Nutrition, NutriscoreGrade, Product } from "./api";

export const PREFERENCES_KEY = "labellens.preferences.v1";
export const PREFERENCES_CHANGED = "labellens:preferences";
export const MAX_AVOIDED = 50;

/** The nutrients someone can set a per-100 g limit on, in the order the form shows them. */
export const LIMITS = [
  { key: "sugars_100g", name: "Sugars", short: "sugars" },
  { key: "salt_100g", name: "Salt", short: "salt" },
  { key: "saturated_fat_100g", name: "Saturated fat", short: "saturated fat" },
] as const satisfies readonly { key: keyof Nutrition; name: string; short: string }[];
export type LimitKey = (typeof LIMITS)[number]["key"];

export const GRADES: NutriscoreGrade[] = ["a", "b", "c", "d", "e"];

export type AvoidedAdditive = { id: string; name: string; e_number: string | null };

export type Preferences = {
  limits: Partial<Record<LimitKey, number>>;
  /** The worst Nutri-Score someone accepts: "b" means A or B. */
  minGrade: NutriscoreGrade | null;
  avoidUltraProcessed: boolean;
  avoidAdditives: AvoidedAdditive[];
};

export const NO_PREFERENCES: Preferences = {
  limits: {},
  minGrade: null,
  avoidUltraProcessed: false,
  avoidAdditives: [],
};

const MAX_GRAMS = 100;

function cleanLimit(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= MAX_GRAMS
    ? value
    : undefined;
}

function cleanText(value: unknown, max = 120): string | null {
  return typeof value === "string" && value.trim() && value.length <= max ? value.trim() : null;
}

/** Preferences from storage or anywhere else untrusted: anything malformed is dropped. */
export function cleanPreferences(raw: unknown): Preferences {
  if (typeof raw !== "object" || raw === null) return NO_PREFERENCES;
  const r = raw as Record<string, unknown>;
  const rawLimits = (typeof r.limits === "object" && r.limits !== null ? r.limits : {}) as Record<
    string,
    unknown
  >;
  const limits: Preferences["limits"] = {};
  for (const { key } of LIMITS) {
    const value = cleanLimit(rawLimits[key]);
    if (value !== undefined) limits[key] = value;
  }
  const minGrade = GRADES.includes(r.minGrade as NutriscoreGrade) ? (r.minGrade as NutriscoreGrade) : null;
  const avoidAdditives: AvoidedAdditive[] = [];
  for (const item of Array.isArray(r.avoidAdditives) ? r.avoidAdditives : []) {
    const a = (typeof item === "object" && item !== null ? item : {}) as Record<string, unknown>;
    const id = cleanText(a.id);
    const name = cleanText(a.name);
    if (!id || !name || avoidAdditives.some((x) => x.id === id)) continue;
    avoidAdditives.push({ id, name, e_number: cleanText(a.e_number, 16) });
    if (avoidAdditives.length === MAX_AVOIDED) break;
  }
  return { limits, minGrade, avoidUltraProcessed: r.avoidUltraProcessed === true, avoidAdditives };
}

export function hasRules(p: Preferences): boolean {
  return (
    Object.keys(p.limits).length > 0 ||
    p.minGrade !== null ||
    p.avoidUltraProcessed ||
    p.avoidAdditives.length > 0
  );
}

export function readPreferences(storage: Storage | undefined = globalThis.localStorage): Preferences {
  try {
    return cleanPreferences(JSON.parse(storage?.getItem(PREFERENCES_KEY) ?? "null"));
  } catch {
    return NO_PREFERENCES;
  }
}

export function writePreferences(
  p: Preferences,
  storage: Storage | undefined = globalThis.localStorage,
): Preferences {
  const clean = cleanPreferences(p);
  try {
    if (hasRules(clean)) storage?.setItem(PREFERENCES_KEY, JSON.stringify(clean));
    else storage?.removeItem(PREFERENCES_KEY);
  } catch {
    // Storage full or blocked (private browsing): the rules last for this page only.
  }
  globalThis.dispatchEvent?.(new Event(PREFERENCES_CHANGED));
  return clean;
}

export const clearPreferences = (storage?: Storage) => writePreferences(NO_PREFERENCES, storage);

// --- Checking a product -------------------------------------------------------------------

export type Outcome = "meets" | "misses" | "unknown";

export type RuleCheck = {
  key: string;
  /** The rule in words: "Sugars: 10 g or less per 100 g". */
  rule: string;
  /** Short, for lists of misses: "sugars". */
  short: string;
  outcome: Outcome;
  /** What this product has: "It has 12.5 g." */
  detail: string;
};

/** What a rule needs from a product; a label read has no Nutri-Score or NOVA group. */
export type Checkable = Pick<Product, "nutrition" | "nutriscore_grade" | "nova_group"> & {
  additives: Pick<Additive, "additive_id" | "name" | "e_number">[];
};

/** Grams to one decimal, so a near miss is visible: 10.4 g, not 10 g. */
export function grams(value: number): string {
  if (value > 0 && value < 0.05) return "<0.1 g";
  return `${Number(value.toFixed(1))} g`;
}

const additiveName = (a: { e_number: string | null; name: string }) =>
  a.e_number ? `${a.e_number} ${a.name}` : a.name;

/** Each rule someone set, and whether this product meets it, in the form's order. */
export function checkRules(p: Preferences, product: Checkable): RuleCheck[] {
  const checks: RuleCheck[] = [];
  for (const { key, name, short } of LIMITS) {
    const limit = p.limits[key];
    if (limit === undefined) continue;
    const value = product.nutrition[key];
    const rule = `${name}: ${grams(limit)} or less per 100 g`;
    checks.push(
      value === null || value === undefined
        ? { key, rule, short, outcome: "unknown", detail: `The label gives no ${short}.` }
        : {
            key,
            rule,
            short,
            outcome: value <= limit ? "meets" : "misses",
            detail: `It has ${grams(value)}.`,
          },
    );
  }

  if (p.minGrade) {
    const rule =
      p.minGrade === "a" ? "Nutri-Score A" : `Nutri-Score ${p.minGrade.toUpperCase()} or better`;
    const grade = product.nutriscore_grade;
    checks.push(
      grade
        ? {
            key: "grade",
            rule,
            short: "Nutri-Score",
            outcome: GRADES.indexOf(grade) <= GRADES.indexOf(p.minGrade) ? "meets" : "misses",
            detail: `It has ${grade.toUpperCase()}.`,
          }
        : { key: "grade", rule, short: "Nutri-Score", outcome: "unknown", detail: "It has no Nutri-Score." },
    );
  }

  if (p.avoidUltraProcessed) {
    const rule = "Not ultra-processed (NOVA 4)";
    const nova = product.nova_group;
    checks.push(
      nova
        ? {
            key: "nova",
            rule,
            short: "ultra-processed",
            outcome: nova === 4 ? "misses" : "meets",
            detail: `It is NOVA ${nova}.`,
          }
        : { key: "nova", rule, short: "ultra-processed", outcome: "unknown", detail: "It has no NOVA group." },
    );
  }

  if (p.avoidAdditives.length > 0) {
    const avoided = new Set(p.avoidAdditives.map((a) => a.id));
    const found = product.additives.filter((a) => avoided.has(a.additive_id));
    const n = p.avoidAdditives.length;
    checks.push({
      key: "additives",
      rule: n === 1 ? `Without ${additiveName(p.avoidAdditives[0])}` : `Without the ${n} additives you avoid`,
      short: "additives",
      outcome: found.length > 0 ? "misses" : "meets",
      detail:
        found.length > 0
          ? `It lists ${found.map(additiveName).join(", ")}.`
          : "None of them is listed.",
    });
  }
  return checks;
}

export function misses(checks: RuleCheck[]): RuleCheck[] {
  return checks.filter((c) => c.outcome === "misses");
}

/** Every rule met, with nothing unknown. */
export function meetsAll(checks: RuleCheck[]): boolean {
  return checks.length > 0 && checks.every((c) => c.outcome === "meets");
}

/** One line for a compare cell: "Meets all 4", "Misses 2", "Meets 3, 1 not known". */
export function verdict(checks: RuleCheck[]): string {
  const missed = misses(checks).length;
  const unknown = checks.filter((c) => c.outcome === "unknown").length;
  if (missed > 0) return `Misses ${missed}`;
  if (unknown > 0) return `Meets ${checks.length - unknown}, ${unknown} not known`;
  return checks.length === 1 ? "Meets it" : `Meets all ${checks.length}`;
}
