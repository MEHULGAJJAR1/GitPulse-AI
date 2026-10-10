import { describe, expect, it } from "vitest";
import { compact, hours, num, pct, signedPct } from "@/lib/format";

describe("format helpers", () => {
  it("renders missing values as an en dash instead of NaN or 0", () => {
    expect(num(null)).toBe("–");
    expect(num(undefined)).toBe("–");
    expect(pct(null)).toBe("–");
    expect(hours(null)).toBe("–");
    expect(compact(null)).toBe("–");
  });
  it("formats hours across minute, hour and day ranges", () => {
    expect(hours(0.5)).toBe("30m");
    expect(hours(5)).toBe("5.0h");
    expect(hours(30)).toBe("30h");
    expect(hours(72)).toBe("3.0d");
  });
  it("signs percentage changes", () => {
    expect(signedPct(12.345)).toBe("+12.3%");
    expect(signedPct(-4)).toBe("-4.0%");
  });
  it("uses thousands separators and compact notation", () => {
    expect(num(1234567)).toBe("1,234,567");
    expect(compact(22691)).toBe("22.7K");
  });
});
