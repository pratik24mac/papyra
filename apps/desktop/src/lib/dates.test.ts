import { describe, expect, it } from "vitest";
import { effectiveDateFormat, formatDate } from "./dates";

describe("formatDate mirrors the engine", () => {
  it("tokens", () => {
    expect(formatDate("2026-03-05", "D MMMM YYYY")).toBe("5 March 2026");
    expect(formatDate("2026-03-05", "DD/MM/YYYY")).toBe("05/03/2026");
    expect(formatDate("2026-03-22", "MMMM Do, YYYY")).toBe("March 22nd, 2026");
    expect(formatDate("2026-03-11", "Do MMM YY")).toBe("11th Mar 26");
    expect(formatDate("2026-03-05", "dddd, D MMMM YYYY")).toBe("Thursday, 5 March 2026");
    expect(formatDate("2026-03-01", "Do")).toBe("1st"); expect(formatDate("2026-03-13", "Do")).toBe("13th"); expect(formatDate("2026-03-31", "Do")).toBe("31st");
  });
  it("leaves non-dates and strftime formats alone", () => {
    expect(formatDate("not a date", "DD/MM/YYYY")).toBe("not a date");
    expect(formatDate("2026-03-05", "%d %B %Y")).toBe("2026-03-05");
    expect(formatDate(undefined)).toBe("");
  });
  it("precedence: field, then Settings, then template, then default", () => {
    expect(effectiveDateFormat("DD", "MM", "YY")).toBe("DD");
    expect(effectiveDateFormat(undefined, "MM", "YY")).toBe("MM");
    expect(effectiveDateFormat(undefined, null, "YY")).toBe("YY");
    expect(effectiveDateFormat(undefined, null, undefined)).toBe("D MMMM YYYY");
  });
});
