// Merge several templates into one form. Fields sharing an id AND a type are asked once
// ("Common details"); fields unique to a template keep their own group, labelled with the
// template's name; same id with a different type is kept apart under a per-template key.
import type { FieldSchema, GroupSchema, TemplateSummary, Values } from "../api/types";

export const COMMON_GROUP = "__common";

export function conflictKey(fieldId: string, templateId: string): string { return `${fieldId}__${templateId}`; }

interface Occurrence { template: TemplateSummary; field: FieldSchema; group: GroupSchema }

export interface Merged {
  summary: TemplateSummary;                   // synthetic template that drives the form and review
  templates: TemplateSummary[];
  keyFor: (templateId: string, fieldId: string) => string;
  split: (values: Values) => { values: Values; byTemplate: Record<string, Values> };
}

function mergeField(occ: Occurrence[]): FieldSchema {
  const first = occ[0].field;
  return { ...first, required: occ.some((o) => o.field.required), help: first.help ?? occ.find((o) => o.field.help)?.field.help,
           default: occ.find((o) => o.field.default !== undefined)?.field.default };
}

export function mergeTemplates(templates: TemplateSummary[]): Merged {
  if (templates.length === 1) {
    const t = templates[0];
    return { summary: t, templates, keyFor: (_tid, id) => id, split: (values) => ({ values, byTemplate: {} }) };
  }
  const byId = new Map<string, Occurrence[]>();
  for (const t of templates) for (const g of t.groups) for (const f of g.fields) {
    const list = byId.get(f.id) ?? []; list.push({ template: t, field: f, group: g }); byId.set(f.id, list);
  }
  const keys = new Map<string, string>();            // `${tid}|${id}` -> form key
  const common: FieldSchema[] = []; const commonEmail: FieldSchema[] = [];
  const perTemplate = new Map<string, Map<string, FieldSchema[]>>();   // tid -> groupId -> fields
  const groupMeta = new Map<string, GroupSchema>();
  for (const [id, occ] of byId) {
    const sameType = occ.every((o) => o.field.type === occ[0].field.type);
    if (occ.length > 1 && sameType) {
      const f = mergeField(occ);
      (occ[0].group.print === false ? commonEmail : common).push(f);
      for (const o of occ) keys.set(`${o.template.id}|${id}`, id);
      continue;
    }
    for (const o of occ) {
      const key = occ.length > 1 ? conflictKey(id, o.template.id) : id;
      keys.set(`${o.template.id}|${id}`, key);
      const label = occ.length > 1 ? `${o.field.label} (${o.template.name})` : o.field.label;
      const tg = perTemplate.get(o.template.id) ?? new Map(); perTemplate.set(o.template.id, tg);
      const gid = `${o.template.id}::${o.group.id}`; groupMeta.set(gid, o.group);
      (tg.get(gid) ?? tg.set(gid, []).get(gid)!).push({ ...o.field, id: key, label });
    }
  }
  const groups: GroupSchema[] = [];
  if (common.length) groups.push({ id: COMMON_GROUP, label: "Common details", fields: common });
  for (const t of templates) {
    const tg = perTemplate.get(t.id); if (!tg) continue;
    for (const [gid, fields] of tg) {
      const g = groupMeta.get(gid)!;
      if (g.print === false) continue;                                    // email fields are collected below
      groups.push({ id: gid, label: `${g.label} · ${t.name}`, fields });
    }
  }
  const emailFields: FieldSchema[] = [...commonEmail];
  for (const t of templates) for (const [gid, fields] of perTemplate.get(t.id) ?? []) if (groupMeta.get(gid)!.print === false) emailFields.push(...fields);
  if (emailFields.length) groups.push({ id: "__email", label: "Email draft", print: false, fields: emailFields });
  const summary: TemplateSummary = { id: "__batch", version: 0, name: `${templates.length} documents`, description: templates.map((t) => t.name).join(", "),
    groups, source: "bundled", dir: "", status: "ok", problems: [], has_examples: templates.some((t) => t.has_examples) };
  const keyFor = (tid: string, id: string) => keys.get(`${tid}|${id}`) ?? id;
  const split = (values: Values) => {
    const shared: Values = {}; const byTemplate: Record<string, Values> = {};
    for (const t of templates) for (const g of t.groups) for (const f of g.fields) {
      const key = keyFor(t.id, f.id);
      if (key === f.id) shared[f.id] = values[f.id];
      else { (byTemplate[t.id] ??= {})[f.id] = values[key]; }
    }
    return { values: shared, byTemplate };
  };
  return { summary, templates, keyFor, split };
}

/** Example values of every template, mapped onto the merged form's keys; the first template wins. */
export function mergeExamples(merged: Merged, examples: Record<string, Values>): Values {
  const out: Values = {};
  for (const t of merged.templates) {
    const ex = examples[t.id] ?? {};
    for (const g of t.groups) for (const f of g.fields) {
      const key = merged.keyFor(t.id, f.id);
      if (out[key] === undefined && ex[f.id] !== undefined) out[key] = ex[f.id];
    }
  }
  return out;
}
