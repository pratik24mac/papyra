// Pure helpers around the template schema: default values, Ant Design validation rules,
// server-error → form-path mapping, and review formatting. No React, so they are unit-testable.
import type { FieldSchema, GroupSchema, TemplateSummary, Values } from "../api/types";

export type NamePath = (string | number)[];

export interface Rule {
  required?: boolean;
  max?: number;
  min?: number;
  pattern?: RegExp;
  type?: "email" | "url" | "number" | "array";
  message?: string;
  validator?: (_: unknown, value: unknown) => Promise<void>;
}

export function defaultValues(template: TemplateSummary): Values {
  const out: Values = {};
  for (const g of template.groups) for (const f of g.fields) out[f.id] = defaultFor(f);
  return out;
}

export function defaultFor(f: FieldSchema): unknown {
  if (f.default !== undefined) return f.default;
  switch (f.type) {
    case "checkbox": return false;
    case "group_list": return f.required ? [emptyItem(f)] : [];
    case "text_list": return f.required ? [""] : [];
    default: return undefined;
  }
}

export function emptyItem(f: FieldSchema): Values {
  const item: Values = {};
  for (const sf of f.item_fields ?? []) item[sf.id] = defaultFor(sf);
  return item;
}

/** Substitute `{field}` placeholders in a default string (e.g. "Resume — {full_name}"). */
export function expandDefault(template: string, values: Values): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => (values[k] == null ? "" : String(values[k])));
}

export function rulesFor(f: FieldSchema): Rule[] {
  const rules: Rule[] = [];
  const v = f.validation ?? {};
  if (f.required && f.type !== "checkbox" && f.type !== "group_list" && f.type !== "text_list") rules.push({ required: true, message: `${f.label} is required` });
  if (f.type === "email") rules.push({ type: "email", message: "Enter a valid email address" });
  if (f.type === "url") rules.push({ pattern: /^https?:\/\/\S+$/, message: "Must start with http:// or https://" });
  if (v.max_length) rules.push({ max: v.max_length, message: `At most ${v.max_length} characters` });
  if (v.pattern) rules.push({ pattern: new RegExp(v.pattern), message: f.help ?? `Invalid ${f.label.toLowerCase()}` });
  if (f.type === "number") {
    if (v.min !== undefined) rules.push({ validator: async (_, x) => { if (typeof x === "number" && x < v.min!) throw new Error(`Must be at least ${v.min}`); } });
    if (v.max !== undefined) rules.push({ validator: async (_, x) => { if (typeof x === "number" && x > v.max!) throw new Error(`Must be at most ${v.max}`); } });
  }
  if (f.type === "group_list" || f.type === "text_list") {
    const min = v.min_items ?? (f.required ? 1 : 0);
    rules.push({ validator: async (_, x) => {
      const n = Array.isArray(x) ? x.length : 0;
      if (n < min) throw new Error(`Add at least ${min} ${min === 1 ? "entry" : "entries"}`);
      if (v.max_items && n > v.max_items) throw new Error(`At most ${v.max_items} entries`);
    } });
  }
  return rules;
}

/** "experience[0].bullets[1]: longer than 400" → { name: ["experience", 0, "bullets", 1], message } */
export function parseServerError(line: string): { name: NamePath; message: string } {
  const idx = line.indexOf(": ");
  const path = idx < 0 ? line : line.slice(0, idx);
  const message = idx < 0 ? "Invalid value" : line.slice(idx + 2);
  const name: NamePath = [];
  for (const m of path.matchAll(/([A-Za-z_]\w*)|\[(\d+)\]/g)) name.push(m[1] !== undefined ? m[1] : Number(m[2]));
  return { name, message: message.charAt(0).toUpperCase() + message.slice(1) };
}

export function isEmpty(v: unknown): boolean {
  return v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0);
}

/** Groups that are printed into the document (the email group is handled by the email step). */
export function printedGroups(t: TemplateSummary): GroupSchema[] {
  return t.groups.filter((g) => g.print !== false);
}

export function countRequired(t: TemplateSummary): number {
  return t.groups.flatMap((g) => g.fields).filter((f) => f.required).length;
}

export function formatValue(f: FieldSchema, v: unknown): string {
  if (isEmpty(v)) return "—";
  if (f.type === "checkbox") return v ? "Yes" : "No";
  if (f.type === "select") {
    const o = (f.options ?? []).find((x) => (typeof x === "string" ? x : x.value) === v);
    return o ? (typeof o === "string" ? o : o.label) : String(v);
  }
  return String(v);
}
