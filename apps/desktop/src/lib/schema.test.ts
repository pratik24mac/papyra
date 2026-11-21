import { describe, expect, it } from "vitest";
import { defaultValues, expandDefault, parseServerError, rulesFor, countRequired, formatValue } from "./schema";
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
    expect(r).toEqual([{ required: true, message: "Name is required" }, { max: 5, message: "At most 5 characters" }]);
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
