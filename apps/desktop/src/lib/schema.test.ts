import { describe, expect, it } from "vitest";
import { defaultValues, defaultFor, expandDefault, parseServerError, rulesFor, countRequired, formatValue } from "./schema";
import type { FieldSchema, TemplateSummary } from "../api/types";

const tpl: TemplateSummary = {
  source: "bundled", dir: "/t", status: "ok", problems: [], has_examples: true,
  id: "t", version: 1, name: "T", description: "",
  groups: [{ id: "g", label: "G", fields: [
    { id: "name", label: "Name", type: "text", required: true, validation: { max_length: 5 } },
    { id: "agree", label: "Agree", type: "checkbox" },
    { id: "jobs", label: "Jobs", type: "group_list", required: true, validation: { max_items: 2 }, item_fields: [{ id: "title", label: "Title", type: "text", required: true }] },
    { id: "notes", label: "Notes", type: "text_list" },
    { id: "subject", label: "Subject", type: "text", default: "Resume — {name}" },
  ] }],
};

describe("defaults", () => {
  it("creates one empty item for required lists and false for checkboxes", () => {
    expect(defaultValues(tpl)).toEqual({ name: undefined, agree: false, jobs: [{ title: undefined }], notes: [], subject: "Resume — {name}" });
  });
  it("expands {field} placeholders", () => {
    expect(expandDefault("Resume — {name}", { name: "Zoë" })).toBe("Resume — Zoë");
    expect(expandDefault("{missing}", {})).toBe("");
  });
});

describe("rules", () => {
  it("maps required/max_length", () => {
    const r = rulesFor(tpl.groups[0].fields[0]);
    expect(r).toEqual([{ required: true, whitespace: true, message: "Name is required" }, { max: 5, message: "At most 5 characters" }]);
  });
  it("validates list sizes", async () => {
    const [rule] = rulesFor(tpl.groups[0].fields[2]);
    await expect(rule.validator!(null, [])).rejects.toThrow("Add at least 1 entry");
    await expect(rule.validator!(null, [1, 2, 3])).rejects.toThrow("At most 2 entries");
    await expect(rule.validator!(null, [1])).resolves.toBeUndefined();
  });
  it("email and url", () => {
    expect(rulesFor({ id: "e", label: "E", type: "email" })[0].type).toBe("email");
    expect(rulesFor({ id: "u", label: "U", type: "url" })[0].pattern!.test("https://x.y")).toBe(true);
    expect(rulesFor({ id: "u", label: "U", type: "url" })[0].pattern!.test("x.y")).toBe(false);
  });
});

describe("server errors", () => {
  it("parses nested paths", () => {
    expect(parseServerError("experience[0].bullets[1]: longer than 400")).toEqual({ name: ["experience", 0, "bullets", 1], message: "Longer than 400" });
    expect(parseServerError("full_name: required")).toEqual({ name: ["full_name"], message: "Required" });
  });
});

describe("misc", () => {
  it("counts required and formats values", () => {
    expect(countRequired(tpl)).toBe(2);
    const sel: FieldSchema = { id: "s", label: "S", type: "select", options: [{ value: "a", label: "Alpha" }, "b"] };
    expect(formatValue(sel, "a")).toBe("Alpha");
    expect(formatValue(sel, "b")).toBe("b");
    expect(formatValue(tpl.groups[0].fields[1], false)).toBe("No");
    expect(formatValue(tpl.groups[0].fields[0], "")).toBe("—");
  });
});

describe("rules at the boundaries", () => {
  const run = async (f: FieldSchema, v: unknown) => {
    const errs: string[] = [];
    for (const r of rulesFor(f)) {
      if (r.validator) { try { await r.validator({} as never, v); } catch (e) { errs.push((e as Error).message); } continue; }
      if (r.required && (v === undefined || v === null || v === "")) errs.push(String(r.message));
      if (r.max !== undefined && typeof v === "string" && v.length > r.max) errs.push(String(r.message));
      if (r.pattern && typeof v === "string" && !r.pattern.test(v)) errs.push(String(r.message));
    }
    return errs;
  };
  it("max_length: exact length passes, one more fails", async () => {
    const f: FieldSchema = { id: "n", label: "N", type: "text", validation: { max_length: 3 } };
    expect(await run(f, "abc")).toEqual([]); expect(await run(f, "abcd")).toEqual(["At most 3 characters"]);
  });
  it("number min/max are inclusive", async () => {
    const f: FieldSchema = { id: "k", label: "K", type: "number", validation: { min: 0, max: 10 } };
    expect(await run(f, 0)).toEqual([]); expect(await run(f, 10)).toEqual([]);
    expect(await run(f, -1)).toEqual(["Must be at least 0"]); expect(await run(f, 10.01)).toEqual(["Must be at most 10"]);
  });
  it("lists: required means one entry, max_items is inclusive", async () => {
    const f: FieldSchema = { id: "l", label: "L", type: "text_list", required: true, validation: { max_items: 2 }, item: { type: "text" } };
    expect(await run(f, [])).toEqual(["Add at least 1 entry"]); expect(await run(f, ["a", "b"])).toEqual([]);
    expect(await run(f, ["a", "b", "c"])).toEqual(["At most 2 entries"]); expect(await run(f, undefined)).toEqual(["Add at least 1 entry"]);
  });
  it("url and email shapes", async () => {
    const u: FieldSchema = { id: "u", label: "U", type: "url" };
    expect(await run(u, "https://x.y/a?b")).toEqual([]); expect(await run(u, "www.x.y")).toHaveLength(1); expect(await run(u, "https:// x")).toHaveLength(1);
  });
  it("defaults: required group lists start with one empty item, optional ones empty", () => {
    const g: FieldSchema = { id: "g", label: "G", type: "group_list", required: true, item_fields: [{ id: "a", label: "A", type: "text" }, { id: "c", label: "C", type: "checkbox" }] };
    expect(defaultFor(g)).toEqual([{ a: undefined, c: false }]); expect(defaultFor({ ...g, required: false })).toEqual([]);
  });
});
